"""
Enhanced ingestion pipeline using Docling for improved PDF processing.

Run *offline*  ➜  python -m rag_module.ingest_pipeline \
    --bucket my-bucket --prefix raw-notes --index notes-prod

This script processes PDFs using Docling to:
- Extract structured content with proper layout preservation
- Handle tables, charts, and vectorized graphics  
- Generate asset-aware captions using vision models
- Create page-based chunks with citation anchors for precise RAG attribution
- Build enhanced vector store indexes with better context

Features:
• Page-based chunking with citation anchors (e.g., "document.pdf#page-3")
• Asset placeholder substitution with vision captions
• Intelligent asset filtering (removes headers, footers, decorative elements)
• Graceful fallback for documents without page structure
• Rich metadata for improved search and attribution

Usage:
• CLI locally for smoke testing and development
• Batch processing for updating existing document collections
• Production deployment via AWS Lambda (see lambda_entrypoint.py)
"""
from __future__ import annotations
import argparse, asyncio, logging

from rag_module.pdfingestor import S3PDFIngestor
from rag_module.vision_captioner import VisionCaptioner
from rag_module.doc_builder import DocBuilder
from settings import settings
from utils.logging_config import logger

# Configure temp directory for Lambda environment at module load time
import os
if (os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or 
    os.environ.get('LAMBDA_RUNTIME_DIR') or 
    os.environ.get('LAMBDA_TASK_ROOT')):
    os.environ['TMPDIR'] = '/tmp'
    os.environ['TMP'] = '/tmp'
    os.environ['TEMP'] = '/tmp'
    import tempfile
    tempfile.tempdir = '/tmp'
    logger.info("Lambda environment detected at module load in ingest_pipeline, configured temp directory to /tmp")

# Configure logging for the pipeline
logging.basicConfig(level=logging.INFO)


async def ingest_pipeline(bucket: str, prefix: str, *, index_name: str) -> None:
    """
    Enhanced ingestion pipeline using Docling workflow.
    
    Parameters
    ----------
    bucket : str
        S3 bucket containing PDF files
    prefix : str
        S3 prefix to filter files
    index_name : str
        Pinecone index name for vector storage
    """
    logger.info("Starting enhanced ingestion pipeline for s3://%s/%s", bucket, prefix)
    
    try:
        # Ensure we use /tmp in Lambda environment
        import os
        tmp_dir = None
        if (os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or 
            os.environ.get('LAMBDA_RUNTIME_DIR') or 
            os.environ.get('LAMBDA_TASK_ROOT')):
            tmp_dir = '/tmp'
            logger.info("Lambda environment detected, using /tmp for ingestion pipeline")
        
        # Initialize components
        ingestor = S3PDFIngestor(bucket=bucket, prefix=prefix, tmp_dir=tmp_dir)
        captioner = VisionCaptioner(api_key=settings.openai_api_key)
        builder = DocBuilder(index_name=index_name)
        
        # Extract structured documents with assets and page content
        docs = await ingestor.process_all()
        
        if not docs:
            logger.info("No PDFs to ingest under s3://%s/%s", bucket, prefix)
            return

        logger.info("Processing %d documents with enhanced pipeline", len(docs))
        
        total_chunks = 0
        total_assets = 0
        total_pages = 0
        
        # Process each document
        for doc in docs:
            try:
                # Count pages if available
                if doc.pages_content:
                    total_pages += len(doc.pages_content)
                    logger.info(
                        "Document %s has %d pages with page-based content",
                        doc.s3_key, len(doc.pages_content)
                    )
                else:
                    logger.info(
                        "Document %s will use document-level processing (no page content)",
                        doc.s3_key
                    )
                
                # Caption all assets in the document
                if doc.assets:
                    asset_captions = await captioner.caption_assets(doc.assets)
                    total_assets += len(doc.assets)
                    logger.info(
                        "Generated captions for %d assets in %s", 
                        len(asset_captions), doc.s3_key
                    )
                else:
                    asset_captions = {}
                    logger.debug("No assets found in %s", doc.s3_key)
                
                # Build and ingest enhanced document with page-based citations
                chunk_count = builder.build_with_assets(doc, asset_captions)
                total_chunks += chunk_count
                
                processing_method = "page-based" if doc.pages_content else "document-level"
                logger.info(
                    "Successfully processed %s (%s): %d chunks, %d assets",
                    doc.s3_key, processing_method, chunk_count, len(doc.assets)
                )
                
            except Exception as e:
                logger.error("Failed to process document %s: %s", doc.s3_key, e)
                # Continue with other documents rather than failing completely
                continue

        logger.info(
            "Enhanced ingestion complete: %d documents, %d pages, %d chunks, %d assets processed", 
            len(docs), total_pages, total_chunks, total_assets
        )
        
    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        raise


async def ingest_pipeline_legacy(bucket: str, prefix: str, *, index_name: str) -> None:
    """
    Legacy ingestion pipeline for backward compatibility.
    
    This method uses the old workflow but with enhanced error handling.
    """
    logger.info("Starting legacy ingestion pipeline for s3://%s/%s", bucket, prefix)
    
    # Ensure we use /tmp in Lambda environment
    import os
    tmp_dir = None
    if (os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or 
        os.environ.get('LAMBDA_RUNTIME_DIR') or 
        os.environ.get('LAMBDA_TASK_ROOT')):
        tmp_dir = '/tmp'
        logger.info("Lambda environment detected, using /tmp for legacy pipeline")
    
    # extract text + thumbnails
    ingestor = S3PDFIngestor(bucket=bucket, prefix=prefix, tmp_dir=tmp_dir)
    docs = await ingestor.process_all()

    if not docs:
        logger.info("No PDFs to ingest under s3://%s/%s", bucket, prefix)
        return

    # caption thumbnails (uses presigned URLs under the hood)
    captioner = VisionCaptioner(api_key=settings.openai_api_key)

    for doc in docs:
        try:
            # Extract image bytes for legacy interface
            if hasattr(doc, 'assets') and doc.assets:
                images = [asset.image_bytes for asset in doc.assets]
            else:
                images = getattr(doc, 'images', [])
                
            captions = await captioner.caption_images(images)
            
            # chunk + embed + upsert
            builder = DocBuilder(index_name=index_name)
            builder.build(doc, captions)
            
        except Exception as e:
            logger.error("Failed to process document %s: %s", doc.s3_key, e)
            continue

    logger.info("Legacy ingest complete: %d documents processed", len(docs))


# CLI
if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Enhanced PDF ingestion pipeline using Docling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all PDFs with enhanced page-based pipeline
  python -m rag_module.ingest_pipeline --bucket my-bucket --prefix docs --index my-index
  
  # Use legacy pipeline for compatibility
  python -m rag_module.ingest_pipeline --bucket my-bucket --prefix docs --index my-index --legacy

Features in Enhanced Mode:
  • Page-based chunking with citation anchors (document.pdf#page-3)
  • Intelligent asset filtering and vision captioning
  • Structured markdown with proper asset placement
  • Rich metadata for precise RAG attribution
        """
    )
    p.add_argument("--bucket", required=True, help="S3 bucket name")
    p.add_argument("--prefix", required=True, help="S3 prefix to filter files")
    p.add_argument("--index", required=True, help="Pinecone index name")
    p.add_argument("--legacy", action="store_true", 
                   help="Use legacy pipeline for backward compatibility")
    
    args = p.parse_args()
    
    # Select pipeline based on arguments
    if args.legacy:
        logger.info("Using legacy pipeline as requested")
        pipeline_func = ingest_pipeline_legacy
    else:
        logger.info("Using enhanced Docling-based pipeline")
        pipeline_func = ingest_pipeline
    
    asyncio.run(pipeline_func(args.bucket, args.prefix, index_name=args.index))

