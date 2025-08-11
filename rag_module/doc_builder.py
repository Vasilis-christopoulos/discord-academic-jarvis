"""
doc_builder.py
──────────────
Enhanced document builder for Docling-based pipeline.

Processes structured documents with asset placeholders and substitutes
vision captions to create cohesive content for vector storage.

Key Features
────────────
• Placeholder substitution for assets (images, tables, figures)
• Intelligent content merging that preserves document structure
• Backward compatibility with legacy text + caption workflow
• Enhanced metadata preservation

Dependencies
────────────
• utils.vector_store.get_vector_store  – wraps Pinecone init / index creation
• langchain_text_splitters.RecursiveCharacterTextSplitter
• rag_module.pdfingestor.IngestedDoc – enhanced document structure
"""

from __future__ import annotations
from typing import List, Dict, Optional, Any
import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_module.ingest_vector_store import get_vector_store
from rag_module.pdfingestor import IngestedDoc, PageContent, ChunkWithCitation, AssetInfo
from utils.logging_config import logger


class DocBuilder:
    def __init__(
        self,
        *,
        index_name: str,
        chunk_size: int = 1_000,
        chunk_overlap: int = 100,
    ) -> None:
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        # single line does all Pinecone init / embedder wiring
        self.vstore = get_vector_store(index_name)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        logger.info(
            "Initialized DocBuilder with index=%s, chunk_size=%d, overlap=%d",
            index_name, chunk_size, chunk_overlap
        )

    def _get_document_name(self, pdoc: IngestedDoc) -> str:
        """Extract document name from metadata or S3 key."""
        return pdoc.metadata.get("filename", pdoc.s3_key.split('/')[-1])

    # Enhanced interface for Docling-based workflow
    def build_with_assets(self, pdoc: IngestedDoc, asset_captions: Dict[str, str]) -> int:
        """
        Build and ingest documents using the enhanced Docling workflow with page-based citations.
        
        Parameters
        ----------
        pdoc : IngestedDoc
            Document from Docling-based pdfingestor with markdown_content and assets
        asset_captions : Dict[str, str]
            Mapping of asset_id -> caption from vision captioner
            
        Returns
        -------
        int : Number of chunks upserted to vector store
        """
        try:
            # Use page-based chunking if page content is available
            if pdoc.pages_content and len(pdoc.pages_content) > 0:
                return self._build_with_page_based_citations(pdoc, asset_captions)
            else:
                # Fallback to document-level processing
                return self._build_document_level(pdoc, asset_captions)
            
        except Exception as e:
            logger.error("Error building document %s: %s", pdoc.s3_key, e)
            raise

    def _build_with_page_based_citations(self, pdoc: IngestedDoc, asset_captions: Dict[str, str]) -> int:
        """
        Build document using page-based chunking with citation anchors.
        
        Returns the number of chunks created.
        """
        # Safety check - should not reach here if pages_content is None due to caller check
        if not pdoc.pages_content:
            logger.warning("_build_with_page_based_citations called with no pages_content, falling back to document level")
            return self._build_document_level(pdoc, asset_captions)
            
        all_docs = []
        document_name = self._get_document_name(pdoc)
        
        # Deduplicate pages by page number - keep the first occurrence of each page
        seen_pages = set()
        unique_pages = []
        duplicates_found = 0
        
        for page_content in pdoc.pages_content:
            page_num = page_content.page_number
            if page_num not in seen_pages:
                seen_pages.add(page_num)
                unique_pages.append(page_content)
            else:
                duplicates_found += 1
                logger.warning(
                    "Skipping duplicate page %d in %s (keeping first occurrence)",
                    page_num, document_name
                )
        
        if duplicates_found > 0:
            logger.warning(
                "Found and skipped %d duplicate pages in %s", 
                duplicates_found, document_name
            )
        
        logger.info(
            "Processing %s with page-based citations: %d unique pages (skipped %d duplicates)",
            document_name, len(unique_pages), duplicates_found
        )
        
        for page_content in unique_pages:
            # Create page-specific asset captions (only for assets on this page)
            page_asset_captions = {}
            for asset in page_content.assets:
                if asset.asset_id in asset_captions:
                    page_asset_captions[asset.asset_id] = asset_captions[asset.asset_id]
            
            # Substitute asset placeholders with captions for this page only
            processed_content = self._substitute_asset_placeholders(
                page_content.markdown_content, page_asset_captions
            )
            
            # Create citation anchor for this page
            citation_anchor = f"{document_name}#page-{page_content.page_number}"
            
            # Base metadata for this page
            base_metadata = {
                "source": pdoc.s3_key,
                "filename": document_name,
                "page_number": page_content.page_number,
                "citation_anchor": citation_anchor,
                "page_count": pdoc.metadata.get("page_count", 0),
                "asset_count": len(page_content.assets),
                "processing_method": "docling_page_based"
            }
            
            # Add document title if available
            if pdoc.metadata.get("title"):
                base_metadata["title"] = pdoc.metadata["title"]
            
            # Split page content into chunks if needed
            chunks = self.splitter.split_text(processed_content)
            
            if not chunks:
                # Handle empty pages
                chunks = ["[Empty page]"]
            
            # Create documents for each chunk
            for chunk_index, chunk in enumerate(chunks):
                chunk_metadata = {
                    **base_metadata,
                    "chunk_index": chunk_index,
                    "chunks_in_page": len(chunks),
                }
                
                # For multi-chunk pages, add chunk suffix to citation
                if len(chunks) > 1:
                    chunk_metadata["citation_anchor"] = f"{citation_anchor}-chunk-{chunk_index + 1}"
                
                all_docs.append(Document(
                    page_content=chunk,
                    metadata=chunk_metadata
                ))
        
        # Add all documents to vector store
        if all_docs:
            self.vstore.add_documents(all_docs)
            
            logger.info(
                "Successfully processed %s: %d unique pages, %d total chunks, %d assets",
                document_name, len(unique_pages), len(all_docs), len(pdoc.assets)
            )
        
        return len(all_docs)

    def _build_document_level(self, pdoc: IngestedDoc, asset_captions: Dict[str, str]) -> int:
        """
        Fallback to document-level processing when page content is not available.
        """
        # Start with the structured markdown content
        content = pdoc.markdown_content
        
        # Substitute asset placeholders with captions
        processed_content = self._substitute_asset_placeholders(content, asset_captions)
        
        # Enhanced metadata
        document_name = self._get_document_name(pdoc)
        metadata = {
            "source": pdoc.s3_key,
            "filename": document_name,
            "citation_anchor": document_name,
            "page_count": pdoc.metadata.get("page_count", 0),
            "asset_count": len(pdoc.assets),
            "processing_method": "docling_document_level"
        }
        
        # Add document title if available
        if pdoc.metadata.get("title"):
            metadata["title"] = pdoc.metadata["title"]
        
        # Create chunks with enhanced metadata
        chunks = self.splitter.split_text(processed_content)
        docs = [
            Document(
                page_content=chunk,
                metadata={**metadata, "chunk": i, "chunk_count": len(chunks)},
            )
            for i, chunk in enumerate(chunks)
        ]
        
        # Add to vector store
        self.vstore.add_documents(docs)
        
        logger.info(
            "Successfully processed document %s: %d chunks, %d assets",
            pdoc.s3_key, len(chunks), len(pdoc.assets)
        )
        
        return len(docs)

    # Legacy interface for backward compatibility  
    def build(self, pdoc, captions: List[str]) -> int:
        """
        Legacy build method for backward compatibility.
        
        Parameters
        ----------
        pdoc : IngestedDoc or legacy doc
            Document object - supports both old and new formats
        captions : List[str]
            List of image captions (legacy format)
            
        Returns
        -------
        int : Number of chunks upserted to vector store
        """
        try:
            # Handle both old and new document formats
            if hasattr(pdoc, 'markdown_content') and pdoc.markdown_content:
                # New format - try to use enhanced method if we have asset structure
                if hasattr(pdoc, 'assets') and pdoc.assets:
                    # Create caption mapping from asset list and caption list
                    asset_captions = {}
                    for i, asset in enumerate(pdoc.assets):
                        if i < len(captions):
                            asset_captions[asset.asset_id] = captions[i]
                    return self.build_with_assets(pdoc, asset_captions)
                else:
                    # Use markdown content with appended captions
                    caption_block = "\n\n".join(f"[IMAGE] {c}" for c in captions).strip()
                    merged = f"{pdoc.markdown_content}\n\n---\n{caption_block}".strip()
            else:
                # Old format - use text attribute
                text_content = getattr(pdoc, 'text', '')
                caption_block = "\n\n".join(f"[IMAGE] {c}" for c in captions).strip()
                merged = f"{text_content}\n\n---\n{caption_block}".strip()

            # Create basic metadata
            metadata = {"source": pdoc.s3_key, "processing_method": "legacy"}

            # Create and add documents
            docs = [
                Document(
                    page_content=chunk,
                    metadata={**metadata, "chunk": i},
                )
                for i, chunk in enumerate(self.splitter.split_text(merged))
            ]
            self.vstore.add_documents(docs)
            
            logger.info("Processed document %s (legacy): %d chunks", pdoc.s3_key, len(docs))
            return len(docs)
            
        except Exception as e:
            logger.error("Error in legacy build for %s: %s", pdoc.s3_key, e)
            raise

    def build_simple_text(self, fallback_doc) -> int:
        """
        Simple text processing for fallback scenarios when Docling fails.
        
        Parameters
        ----------
        fallback_doc : object
            Simple document object with text and source attributes
            
        Returns
        -------
        int : Number of chunks created
        """
        try:
            # Get text content
            text_content = getattr(fallback_doc, 'text', '')
            if not text_content.strip():
                logger.warning("No text content found in fallback document")
                return 0
            
            # Create basic metadata
            metadata = {
                "source": getattr(fallback_doc, 'source', 'unknown'),
                "processing_method": "fallback_simple_text",
                "fallback": True
            }
            
            # Add any additional metadata from the document
            if hasattr(fallback_doc, 'metadata') and isinstance(fallback_doc.metadata, dict):
                metadata.update(fallback_doc.metadata)
            
            # Split text into chunks
            chunks = self.splitter.split_text(text_content)
            
            if not chunks:
                # Fallback for very short content
                chunks = [text_content[:1000]]  # Take first 1000 chars if no chunks created
            
            # Create documents
            docs = [
                Document(
                    page_content=chunk,
                    metadata={**metadata, "chunk_index": i, "total_chunks": len(chunks)},
                )
                for i, chunk in enumerate(chunks)
            ]
            
            # Add to vector store
            self.vstore.add_documents(docs)
            
            logger.info(
                "Successfully processed fallback document %s: %d chunks",
                metadata.get('source', 'unknown'), len(chunks)
            )
            
            return len(docs)
            
        except Exception as e:
            logger.error("Error in simple text processing: %s", str(e))
            raise

    def _substitute_asset_placeholders(self, content: str, asset_captions: Dict[str, str]) -> str:
        """
        Replace asset placeholders in markdown content with actual captions.
        
        Parameters
        ----------
        content : str
            Markdown content with placeholders like {{ASSET:picture_1}} or <!-- image -->
        asset_captions : Dict[str, str]
            Mapping of asset_id -> caption
            
        Returns
        -------
        str : Content with placeholders replaced by formatted captions
        """
        
        def replace_placeholder(match):
            asset_id = match.group(1)
            caption = asset_captions.get(asset_id, f"[Asset: {asset_id}]")
            
            # Format the caption based on asset type
            if asset_id.startswith('picture'):
                return f"\n**Figure:** {caption}\n"
            elif asset_id.startswith('table'):
                return f"\n**Table:** {caption}\n"
            elif asset_id.startswith('formula'):
                return f"\n**Formula:** {caption}\n"
            elif asset_id.startswith('code'):
                return f"\n**Code:** {caption}\n"
            elif asset_id.startswith('figure'):
                return f"\n**Diagram:** {caption}\n"
            elif asset_id.startswith('structured'):
                return f"\n**Structure:** {caption}\n"
            else:
                return f"\n**Asset:** {caption}\n"
        
        processed_content = content
        
        # 1. Replace {{ASSET:asset_id}} placeholders
        pattern = r'\{\{ASSET:([^}]+)\}\}'
        processed_content = re.sub(pattern, replace_placeholder, processed_content)
        
        # 2. Handle legacy <!-- image --> placeholders by replacing them sequentially
        # with available asset captions
        if '<!-- image -->' in processed_content and asset_captions:
            asset_list = list(asset_captions.items())
            asset_index = 0
            
            while '<!-- image -->' in processed_content and asset_index < len(asset_list):
                asset_id, caption = asset_list[asset_index]
                
                # Format the caption based on asset type
                if asset_id.startswith('picture'):
                    replacement = f"\n**Figure:** {caption}\n"
                elif asset_id.startswith('table'):
                    replacement = f"\n**Table:** {caption}\n"
                elif asset_id.startswith('formula'):
                    replacement = f"\n**Formula:** {caption}\n"
                elif asset_id.startswith('code'):
                    replacement = f"\n**Code:** {caption}\n"
                elif asset_id.startswith('figure'):
                    replacement = f"\n**Diagram:** {caption}\n"
                elif asset_id.startswith('structured'):
                    replacement = f"\n**Structure:** {caption}\n"
                else:
                    replacement = f"\n**Asset:** {caption}\n"
                
                # Replace the first occurrence
                processed_content = processed_content.replace('<!-- image -->', replacement, 1)
                asset_index += 1
            
            # Remove any remaining <!-- image --> placeholders
            processed_content = processed_content.replace('<!-- image -->', '')
        
        # 3. Fallback: If no placeholders were found but we have captions, only append them 
        # if there are actually assets that belong to this content (for page-based processing)
        has_asset_placeholders = bool(re.search(r'\{\{ASSET:[^}]+\}\}', content)) or ('<!-- image -->' in content)
        if not has_asset_placeholders and asset_captions:
            # Only append captions if we have a small number of assets (likely page-specific)
            # This prevents the fallback from adding all document assets to every page
            if len(asset_captions) <= 3:  # Conservative threshold
                caption_block = "\n\n---\n**Page Assets:**\n"
                for asset_id, caption in asset_captions.items():
                    if asset_id.startswith('picture'):
                        asset_type = "Figure"
                    elif asset_id.startswith('table'):
                        asset_type = "Table"
                    elif asset_id.startswith('formula'):
                        asset_type = "Formula"
                    elif asset_id.startswith('code'):
                        asset_type = "Code"
                    elif asset_id.startswith('figure'):
                        asset_type = "Diagram"
                    elif asset_id.startswith('structured'):
                        asset_type = "Structure"
                    else:
                        asset_type = "Asset"
                    caption_block += f"\n**{asset_type}:** {caption}\n"
                processed_content += caption_block
            # If there are many assets, it's likely we're processing document-level content
            # and should avoid the fallback to prevent asset duplication
        
        return processed_content
