"""
PDF ingestor using Docling.

Responsibilities
----------------
1. Enumerate documents that live under an S3 prefix.
2. Download them to a local temp dir.
3. Extract text and assets (images, tables, figures) using Docling.
4. Return structured documents with placeholders for assets.
5. Generate markdown content that preserves original layout.

This implementation replaces PyMuPDF with Docling for improved:
- Table structure recognition
- Chart and graph understanding
- Vectorized image handling
- Maintenance of original document layout
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence, Dict, Any, Tuple, Optional
from datetime import datetime
import re

import boto3
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat, DocumentStream
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling_core.types.doc import (
    PictureItem, TableItem, FormulaItem, CodeItem, 
    SectionHeaderItem, ListItem, GroupItem, KeyValueItem,
    FloatingItem, ImageRefMode
)

from utils.logging_config import logger


# Data model - Enhanced with citation support
@dataclass
class AssetInfo:
    """Information about a visual asset extracted from the document for vision captioning.
    
    Only includes truly visual elements that require vision understanding:
    - PictureItem: Photos, charts, diagrams, images of tables/code/formulas
    - Structural figures: Visual diagrams, flowcharts, illustrations
    
    Text-based elements (TableItem, CodeItem, FormulaItem, etc.) are processed 
    as structured text and included directly in the markdown content.
    """
    asset_id: str           # Unique identifier for the asset
    asset_type: str         # Type: 'picture' or 'figure' (visual elements only)
    image_bytes: bytes      # PNG bytes of the asset image
    page_number: int        # Page number where the asset appears
    bbox: Optional[Dict[str, float]] = None  # Bounding box coordinates

@dataclass
class PageContent:
    """Represents content from a single page with citation metadata."""
    page_number: int
    markdown_content: str
    assets: List[AssetInfo] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass 
class ChunkWithCitation:
    """Document chunk with citation information for RAG systems."""
    content: str
    metadata: Dict[str, Any]
    citation_anchor: str
    page_number: int
    chunk_index: int  # Index within the page (for large pages split into multiple chunks)
    document_name: str

@dataclass
class IngestedDoc:
    """Enhanced output of the Docling-based ingestor."""
    s3_key: str                         # Full S3 key (for traceability)
    markdown_content: str               # Markdown with asset placeholders
    assets: List[AssetInfo] = field(default_factory=list)  # All extracted assets
    metadata: Dict[str, Any] = field(default_factory=dict)  # Document metadata
    pages_content: Optional[List[PageContent]] = None  # Page-by-page content for citations

# Main class
class S3PDFIngestor:
    """Pull PDFs from an S3 bucket and extract structured content using Docling.
    
    This class handles downloading PDFs from S3, parsing them with Docling to extract
    text, tables, and images while preserving document structure, and returning
    structured data for further processing.
    
    Parameters
    ----------
    bucket : str
        The name of the S3 bucket containing the PDFs.
    prefix : str, optional
        The S3 prefix to filter files (default is empty, meaning all files).
    max_concurrency : int, optional
        Maximum number of concurrent downloads (default is 4).
    tmp_dir : str | Path, optional
        Temporary directory for storing downloaded PDFs (default is system temp dir).
    image_resolution_scale : float, optional
        Scale factor for extracted images (default is 2.0, i.e., ~144 DPI).
        
    Raises
    ------
    ValueError
        If `bucket` is not a non-empty string.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        *,
        max_concurrency: int = 4,
        tmp_dir: str | Path | None = None,
        image_resolution_scale: float = 2.0,
    ) -> None:
        if not bucket:
            raise ValueError("`bucket` must be a non-empty string")

        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.s3 = boto3.client("s3")
        self.semaphore = asyncio.Semaphore(max_concurrency)
        
        # Use /tmp for Lambda environment, fallback to system temp dir for local development
        if tmp_dir is None:
            # Check if we're in a Lambda environment by looking for common Lambda environment variables
            import os
            lambda_function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
            lambda_runtime_dir = os.environ.get('LAMBDA_RUNTIME_DIR')
            lambda_task_root = os.environ.get('LAMBDA_TASK_ROOT')
            
            logger.info(
                "Lambda environment detection: AWS_LAMBDA_FUNCTION_NAME=%s, LAMBDA_RUNTIME_DIR=%s, LAMBDA_TASK_ROOT=%s", 
                lambda_function_name, lambda_runtime_dir, lambda_task_root
            )
            
            if lambda_function_name or lambda_runtime_dir or lambda_task_root:
                tmp_dir = '/tmp'
                logger.info("Lambda environment detected, using /tmp as temporary directory")
                
                # Set all environment variables to force temp operations to use /tmp
                os.environ['TMPDIR'] = '/tmp'
                os.environ['TMP'] = '/tmp'
                os.environ['TEMP'] = '/tmp'
                os.environ['HOME'] = '/tmp'
                os.environ['TRANSFORMERS_CACHE'] = '/tmp/.cache/huggingface'
                os.environ['HF_HOME'] = '/tmp/.cache/huggingface'
                os.environ['XDG_CACHE_HOME'] = '/tmp/.cache'
                os.environ['TORCH_HOME'] = '/tmp/.cache/torch'
                os.environ['NUMBA_CACHE_DIR'] = '/tmp/.cache/numba'
                
                # Create cache directories if they don't exist
                cache_dirs = [
                    '/tmp/.cache',
                    '/tmp/.cache/huggingface',
                    '/tmp/.cache/torch',
                    '/tmp/.cache/numba'
                ]
                for cache_dir in cache_dirs:
                    Path(cache_dir).mkdir(parents=True, exist_ok=True)
                    
                logger.info("Set environment variables and created cache directories in /tmp")
            else:
                tmp_dir = tempfile.gettempdir()
                logger.info("Local environment detected, using system temp dir: %s", tmp_dir)
        else:
            logger.info("Using provided tmp_dir: %s", tmp_dir)
        
        self.tmp_root = Path(tmp_dir) / "jarvis_ingest"
        logger.info("Creating temporary directory: %s", self.tmp_root)
        self.tmp_root.mkdir(exist_ok=True)
        self.image_resolution_scale = image_resolution_scale
        
        # Configure Docling pipeline options
        self.pipeline_options = PdfPipelineOptions()
        self.pipeline_options.images_scale = image_resolution_scale
        self.pipeline_options.generate_page_images = True
        self.pipeline_options.generate_picture_images = True
        self.pipeline_options.generate_table_images = True
        
        # Initialize document converter
        self.doc_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=self.pipeline_options)
            }
        )
        
        # Asset filtering thresholds (to reduce unnecessary asset extraction)
        self.min_asset_area = 1000  # Minimum area in pixels² (more lenient: ~32x32)
        self.min_asset_bytes = 2000  # Minimum file size in bytes (more lenient)
        self.max_aspect_ratio = 15   # Skip very narrow/wide assets (decorative lines)
        
        logger.info(
            "Initialized S3PDFIngestor with bucket=%s, prefix=%s, image_scale=%.1f", 
            bucket, prefix, image_resolution_scale
        )

    # public API
    async def process_all(self) -> List[IngestedDoc]:
        """Download every PDF under the prefix and return parsed docs."""
        keys = self._list_keys(".pdf")
        logger.info("Found %d PDF files to process", len(keys))
        
        coros = [self._process_single(k) for k in keys]
        results = await asyncio.gather(*coros)
        
        logger.info("Successfully processed %d PDF documents", len(results))
        return results
    
    async def process_key(self, key: str) -> IngestedDoc:
        """Public helper: parse ONE S3 object key."""
        return await self._process_single(key)

    # internals
    def _list_keys(self, suffix: str) -> Sequence[str]:
        """List S3 objects whose key ends-with `suffix`."""
        paginator = self.s3.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.lower().endswith(suffix):
                    keys.append(key)
        logger.debug("Found %d files with suffix '%s'", len(keys), suffix)
        return keys

    async def _process_single(self, key: str) -> IngestedDoc:
        """Download → parse → return a single document."""
        async with self.semaphore:
            try:
                local_path = await asyncio.to_thread(self._download_to_tmp, key)
                try:
                    result = await asyncio.to_thread(self._parse_pdf_with_docling, local_path, key)
                    logger.info("Successfully processed document: %s", key)
                    return result
                except Exception as e:
                    logger.error("Failed to parse PDF %s: %s", key, e)
                    raise
                finally:
                    local_path.unlink(missing_ok=True)
            except Exception as e:
                logger.error("Failed to process document %s: %s", key, e)
                raise

    def _download_to_tmp(self, key: str) -> Path:
        """Blocking S3 download (run in thread-pool)."""
        local = self.tmp_root / Path(key).name
        logger.debug("Downloading %s to %s", key, local)
        self.s3.download_file(self.bucket, key, str(local))
        return local

    def _parse_pdf_with_docling(self, path: Path, s3_key: str) -> IngestedDoc:
        """Extract structured content from PDF using Docling."""
        try:
            # Log current working directory and temp settings
            import os
            logger.info("Current working directory: %s", os.getcwd())
            logger.info("tempfile.gettempdir(): %s", tempfile.gettempdir())
            logger.info("TMPDIR env var: %s", os.environ.get('TMPDIR'))
            logger.info("TMP env var: %s", os.environ.get('TMP'))
            logger.info("TEMP env var: %s", os.environ.get('TEMP'))
            logger.info("Processing PDF file: %s", path)
            
            # Convert PDF using Docling
            logger.info("Starting Docling conversion...")
            conv_result = self.doc_converter.convert(path)
            logger.info("Docling conversion completed successfully")
            doc = conv_result.document
            
            # Extract metadata
            metadata = {
                "filename": path.name,
                "page_count": len(doc.pages),
                "title": getattr(doc, 'title', None) or path.stem,
            }
            
            # First pass: collect all elements with their positions for analysis
            all_elements = []
            page_dimensions = {}
            
            logger.debug("Starting document element iteration")
            for element, level in doc.iterate_items():
                # Try to determine page from bbox if page_no is not available
                page_no = getattr(element, 'page_no', None)
                bbox = None
                
                logger.debug("Processing element: %s, page_no=%s, is_asset=%s", 
                           type(element).__name__, page_no, 
                           isinstance(element, (PictureItem, TableItem, FormulaItem, CodeItem, 
                                              SectionHeaderItem, ListItem, GroupItem, KeyValueItem, FloatingItem)))
                
                if hasattr(element, 'prov') and element.prov:
                    prov = element.prov[0] if element.prov else None
                    if prov and hasattr(prov, 'bbox'):
                        bbox = {
                            'left': prov.bbox.l,
                            'top': prov.bbox.t, 
                            'right': prov.bbox.r,
                            'bottom': prov.bbox.b
                        }
                        # If page_no is unknown, try to infer from position using bbox
                        if page_no is None and prov and hasattr(prov, 'page_no'):
                            page_no = prov.page_no
                
                # If still no page number, try to infer from bbox coordinates
                if page_no is None and bbox and hasattr(doc, 'pages') and len(doc.pages) > 1:
                    page_no = self._infer_page_from_bbox(bbox, doc)
                
                if page_no is None:
                    page_no = 1  # Default to page 1 only as last resort
                
                # Ensure page_no is valid
                page_no = max(1, min(page_no, len(doc.pages)))
                
                logger.debug("Final page_no: %d (doc has %d pages)", page_no, len(doc.pages))
                
                all_elements.append({
                    'element': element,
                    'level': level,
                    'page_no': page_no,
                    'bbox': bbox,
                    'is_asset': isinstance(element, (PictureItem, TableItem, FormulaItem, CodeItem, 
                                                   SectionHeaderItem, ListItem, GroupItem, KeyValueItem, FloatingItem))
                })
                
                # Track page dimensions - use page_no as 1-indexed
                if page_no not in page_dimensions and hasattr(doc, 'pages') and 1 <= page_no <= len(doc.pages):
                    try:
                        logger.debug("Getting page dimensions for page %d", page_no)
                        page = doc.pages[page_no - 1]  # Convert to 0-indexed for list access
                        if hasattr(page, 'size') and page.size and hasattr(page.size, 'width') and hasattr(page.size, 'height'):
                            page_dimensions[page_no] = {
                                'width': page.size.width,
                                'height': page.size.height
                            }
                            logger.debug("Got page %d dimensions: %dx%d", page_no, page.size.width, page.size.height)
                        else:
                            page_dimensions[page_no] = {'width': 600, 'height': 800}  # Default
                            logger.debug("Using default dimensions for page %d", page_no)
                    except (IndexError, KeyError, AttributeError) as e:
                        logger.warning("Failed to get page dimensions for page %d: %s", page_no, e)
                        page_dimensions[page_no] = {'width': 600, 'height': 800}  # Default
            
            # Second pass: filter and analyze assets
            assets = []
            asset_counter = 0
            
            # Group elements by page for header/footer detection
            elements_by_page = {}
            for elem_info in all_elements:
                page_no = elem_info['page_no']
                if page_no not in elements_by_page:
                    elements_by_page[page_no] = []
                elements_by_page[page_no].append(elem_info)
            
            # Detect recurring header/footer assets across pages
            recurring_assets = self._detect_recurring_assets(elements_by_page, page_dimensions)
            
            # Process assets with enhanced filtering - only send visual elements to vision captioner
            for elem_info in all_elements:
                if not elem_info['is_asset']:
                    continue
                    
                element = elem_info['element']
                bbox = elem_info['bbox']
                page_no = elem_info['page_no']
                
                # Only process truly visual elements for vision captioning
                # TableItem, CodeItem, FormulaItem should be processed as text/markdown by DocBuilder
                if isinstance(element, PictureItem):
                    # Pictures always need vision captioning (could be photos, charts, images of tables/code, etc.)
                    asset_type = "picture"
                    asset_counter += 1
                elif isinstance(element, (SectionHeaderItem, GroupItem, FloatingItem)):
                    # Structural elements that are likely visual figures/diagrams
                    asset_type = "figure"
                    asset_counter += 1
                else:
                    # Skip TableItem, CodeItem, FormulaItem, ListItem, KeyValueItem
                    # These should be processed as structured text by DocBuilder, not vision captioned
                    logger.debug("Skipping text-based element for vision captioning: %s (page %d)", 
                               type(element).__name__, page_no)
                    continue
                    
                asset_id = f"{asset_type}_{asset_counter}"
                
                try:
                    # Calculate dimensions and area
                    width, height, area = 0, 0, 0
                    if bbox:
                        # Handle PDF coordinate system properly
                        width = abs(bbox['right'] - bbox['left'])
                        height = abs(bbox['bottom'] - bbox['top'])
                        area = width * height
                    
                    # Apply comprehensive filtering
                    filter_reasons = []
                    
                    # Log asset details for debugging
                    logger.debug("Asset %s: type=%s, area=%.0f, dims=%.0fx%.0f, page=%d, pos=(%.0f,%.0f)", 
                              asset_id, asset_type, area, width, height, page_no, 
                              bbox['left'] if bbox else 0, bbox['top'] if bbox else 0)
                    
                    # 1. Minimum area filter (removes small decorative elements like bullets, icons)
                    if area > 0 and area < self.min_asset_area:
                        filter_reasons.append(f"too small (area={area:.0f} < {self.min_asset_area})")
                    
                    # 1b. Small square filter (removes bullet points and small icons)
                    if width > 0 and height > 0 and max(width, height) < 120:  # Assets smaller than 120px in any dimension
                        filter_reasons.append(f"small decorative element (max_dim={max(width, height):.0f} < 120)")
                    
                    # 2. Aspect ratio filter (removes decorative lines)
                    if width > 0 and height > 0:
                        aspect_ratio = max(width/height, height/width)
                        if aspect_ratio > self.max_aspect_ratio:
                            filter_reasons.append(f"extreme aspect ratio ({aspect_ratio:.1f})")
                    
                    # 3. Header/footer position filter  
                    # Note: PDF coordinate system has Y=0 at bottom, but assets may be reported differently
                    if bbox and page_no in page_dimensions:
                        page_height = page_dimensions[page_no]['height']
                        y_position = bbox['top']
                        
                        logger.debug("Page %d: height=%d, y_pos=%.0f", page_no, page_height, y_position)
                        
                        # Very conservative header/footer detection
                        # Only filter obvious header elements that are way outside the page bounds
                        # or very small decorative elements in extreme positions
                        
                        # Header detection: y significantly > page height (coordinate overflow)
                        if y_position > page_height * 1.3:  # 30% beyond page height
                            filter_reasons.append(f"in header region (y={y_position:.0f}, page_h={page_height})")
                        # Footer detection: y < 3% of page height (very bottom)
                        elif y_position < page_height * 0.03:
                            filter_reasons.append(f"in footer region (y={y_position:.0f}, page_h={page_height})")
                    
                    # 4. Very small dimension filter
                    if width > 0 and height > 0 and (width < 20 or height < 20):
                        filter_reasons.append(f"dimension too small (w={width:.0f}, h={height:.0f})")
                    
                    # 5. Recurring asset filter (logos, page numbers, etc.)
                    asset_key = f"{asset_type}_{width:.0f}x{height:.0f}"
                    if asset_key in recurring_assets and recurring_assets[asset_key]['count'] >= 3:
                        # This asset appears frequently in similar positions - likely decorative
                        filter_reasons.append(f"recurring decorative element (appears {recurring_assets[asset_key]['count']} times)")
                    
                    # Skip asset if any filter criteria are met
                    if filter_reasons:
                        logger.debug("Filtered out asset %s: %s", asset_id, "; ".join(filter_reasons))
                        continue
                    
                    # Get the image for this element (if available)
                    image = None
                    image_bytes = None
                    
                    # Try to get image representation
                    if hasattr(element, 'get_image') and callable(getattr(element, 'get_image')):
                        try:
                            image = element.get_image(doc)
                        except Exception as e:
                            logger.debug("Failed to get image for %s: %s", asset_id, e)
                    
                    # Handle different content types
                    if image:
                        # Convert PIL image to bytes
                        import io
                        img_buffer = io.BytesIO()
                        image.save(img_buffer, format='PNG', optimize=True)
                        image_bytes = img_buffer.getvalue()
                        
                        # Apply file size filter for image assets
                        if len(image_bytes) < self.min_asset_bytes:
                            logger.debug("Filtered out asset %s: file too small (%d bytes)", 
                                       asset_id, len(image_bytes))
                            continue
                            
                    elif asset_type in ["formula", "code", "structured"]:
                        # For text-based assets, create a simple placeholder image or extract text
                        try:
                            if hasattr(element, 'text') and element.text:
                                # Create a minimal image placeholder or store text content
                                # For now, we'll create a simple text-based placeholder
                                placeholder_text = f"[{asset_type.upper()}]: {element.text[:100]}..."
                                
                                # Create a simple image with the text (optional - for vision captioning)
                                # Or just use text content directly in markdown
                                from PIL import Image, ImageDraw, ImageFont
                                img = Image.new('RGB', (400, 100), color='white')
                                draw = ImageDraw.Draw(img)
                                try:
                                    # Try to use a default font
                                    font = ImageFont.load_default()
                                except:
                                    font = None
                                
                                # Wrap text if too long
                                wrapped_text = placeholder_text[:50] + "..." if len(placeholder_text) > 50 else placeholder_text
                                draw.text((10, 10), wrapped_text, fill='black', font=font)
                                
                                # Convert to bytes
                                import io
                                img_buffer = io.BytesIO()
                                img.save(img_buffer, format='PNG')
                                image_bytes = img_buffer.getvalue()
                            else:
                                # Skip assets without content
                                logger.debug("Skipping %s asset %s: no content available", asset_type, asset_id)
                                continue
                        except Exception as e:
                            logger.debug("Failed to create placeholder for %s: %s", asset_id, e)
                            continue
                    else:
                        logger.debug("Skipping asset %s: no image data available", asset_id)
                        continue
                    
                    if image_bytes:
                        assets.append(AssetInfo(
                            asset_id=asset_id,
                            asset_type=asset_type,
                            image_bytes=image_bytes,
                            page_number=page_no,
                            bbox=bbox
                        ))
                        
                        logger.info("Added %s asset: %s to page %d (%.0fx%.0f, %d bytes)", 
                                   asset_type, asset_id, page_no, width, height, len(image_bytes))
                    else:
                        logger.debug("Skipping asset %s: failed to generate content", asset_id)
                except Exception as e:
                    logger.warning("Failed to extract image for %s: %s", asset_id, e)
                    continue
            
            logger.info("Asset extraction: %d assets extracted after filtering", len(assets))
            
            # Generate markdown with placeholders in correct reading order
            markdown_content = self._generate_markdown_with_ordered_placeholders(doc, assets, all_elements)
            
            logger.info(
                "Parsed PDF: %d pages, %d assets, %d chars of markdown", 
                len(doc.pages), len(assets), len(markdown_content)
            )
            
            # Extract page-by-page content for citation support
            pages_content = self._extract_page_contents(doc, assets)
            
            return IngestedDoc(
                s3_key=s3_key,
                markdown_content=markdown_content,
                assets=assets,
                metadata=metadata,
                pages_content=pages_content
            )
            
        except Exception as e:
            logger.error("Error parsing PDF with Docling: %s", e)
            raise
    
    
    def _detect_recurring_assets(self, elements_by_page, page_dimensions):
        """Detect assets that appear repeatedly across pages (likely headers/footers/logos)."""
        asset_patterns = {}
        
        for page_no, elements in elements_by_page.items():
            page_height = page_dimensions.get(page_no, {}).get('height', 800)
            
            for elem_info in elements:
                if not elem_info['is_asset']:
                    continue
                    
                element = elem_info['element']
                bbox = elem_info['bbox']
                
                if not bbox:
                    continue
                
                # Create a pattern key based on size and relative position
                width = abs(bbox['right'] - bbox['left'])
                height = abs(bbox['bottom'] - bbox['top'])
                
                # Normalize position relative to page height
                y_position_rel = bbox['top'] / page_height if page_height > 0 else 0
                
                # Create pattern key - assets with similar size and relative position
                pattern_key = f"{isinstance(element, PictureItem)}_{width:.0f}x{height:.0f}_{y_position_rel:.2f}"
                
                if pattern_key not in asset_patterns:
                    asset_patterns[pattern_key] = {
                        'count': 0,
                        'pages': [],
                        'positions': []
                    }
                
                asset_patterns[pattern_key]['count'] += 1
                asset_patterns[pattern_key]['pages'].append(page_no)
                asset_patterns[pattern_key]['positions'].append((bbox['left'], bbox['top']))
        
        # Return patterns that appear on multiple pages
        recurring = {}
        for pattern, info in asset_patterns.items():
            if info['count'] >= 2:  # Appears on 2+ pages
                # Use a simpler key for filtering
                size_key = pattern.split('_')[1]  # Extract size part
                recurring[size_key] = info
        
        logger.debug("Detected %d recurring asset patterns", len(recurring))
        return recurring

    def _generate_markdown_with_ordered_placeholders(self, doc, assets: List[AssetInfo], all_elements) -> str:
        """Generate markdown content with properly ordered asset placeholders."""
        try:
            # Get base markdown from Docling
            base_markdown = doc.export_to_markdown()
            
            # Create a reading-order map of assets based on their positions
            assets_by_position = {}
            
            # Sort assets by page, then by vertical position (top to bottom), then horizontal (left to right)
            sorted_assets = sorted(assets, key=lambda a: (
                a.page_number,
                -a.bbox['top'] if a.bbox else 0,  # Negative for top-to-bottom order
                a.bbox['left'] if a.bbox else 0
            ))
            
            # Create position-based mapping
            for i, asset in enumerate(sorted_assets):
                assets_by_position[i] = asset
            
            # Replace generic placeholders with specific asset placeholders in reading order
            processed_markdown = base_markdown
            
            # Pattern for generic image placeholders from Docling
            patterns_to_replace = [
                r'<!-- image -->',
                r'<img[^>]*>',  # HTML img tags
                r'!\[.*?\]\([^)]*\)',  # Markdown image syntax
            ]
            
            asset_index = 0
            for pattern in patterns_to_replace:
                import re
                while re.search(pattern, processed_markdown) and asset_index < len(sorted_assets):
                    # Replace with the next asset in reading order
                    asset = sorted_assets[asset_index]
                    asset_placeholder = f"{{{{ASSET:{asset.asset_id}}}}}"
                    processed_markdown = re.sub(pattern, asset_placeholder, processed_markdown, count=1)
                    asset_index += 1
            
            # If there are remaining generic placeholders but no more assets, remove them
            for pattern in patterns_to_replace:
                processed_markdown = re.sub(pattern, "", processed_markdown)
            
            # If there are remaining assets that weren't placed, add them at logical positions
            if asset_index < len(sorted_assets):
                logger.warning("Some assets (%d) were not placed in markdown content", 
                             len(sorted_assets) - asset_index)
                
                # Group remaining assets by page and insert them appropriately
                remaining_by_page = {}
                for i in range(asset_index, len(sorted_assets)):
                    asset = sorted_assets[i]
                    page = asset.page_number
                    if page not in remaining_by_page:
                        remaining_by_page[page] = []
                    remaining_by_page[page].append(asset)
                
                # Insert remaining assets at page boundaries or end
                for page, page_assets in remaining_by_page.items():
                    for asset in page_assets:
                        placeholder = f"{{{{ASSET:{asset.asset_id}}}}}"
                        processed_markdown += f"\n\n{placeholder}"
            
            # Clean up any excessive newlines
            processed_markdown = re.sub(r'\n{3,}', '\n\n', processed_markdown)
            
            logger.debug("Markdown generation: placed %d assets in reading order", asset_index)
            return processed_markdown
            
        except Exception as e:
            logger.error("Error generating markdown with ordered placeholders: %s", e)
            # Fallback to basic markdown without placeholders
            return doc.export_to_markdown()
    
    def _extract_page_contents(self, doc, assets: List[AssetInfo]) -> List[PageContent]:
        """
        Extract content for each page using Docling's structured document model.
        
        This method properly extracts page-by-page content by:
        1. Iterating through document elements that have page assignments
        2. Grouping content by actual page numbers from Docling
        3. Maintaining proper document structure and reading order
        4. Associating assets with their correct source pages only
        """
        pages_content = []
        
        try:
            logger.info("Extracting page contents using Docling document structure")
            
            # Group document elements by page number
            elements_by_page = {}
            
            # Iterate through all document elements and group by page
            for element, level in doc.iterate_items():
                # Get the page number for this element
                page_no = getattr(element, 'page_no', None)
                
                # If page_no is not available, try to get it from provenance
                if page_no is None and hasattr(element, 'prov') and element.prov:
                    prov = element.prov[0] if element.prov else None
                    if prov and hasattr(prov, 'page_no'):
                        page_no = prov.page_no
                    # Also try to get bbox for coordinate-based inference
                    elif prov and hasattr(prov, 'bbox'):
                        bbox = {
                            'left': prov.bbox.l,
                            'top': prov.bbox.t, 
                            'right': prov.bbox.r,
                            'bottom': prov.bbox.b
                        }
                        # Infer page from bbox coordinates if available
                        if hasattr(doc, 'pages') and len(doc.pages) > 1:
                            page_no = self._infer_page_from_bbox(bbox, doc)
                
                # Default to page 1 if we can't determine the page
                if page_no is None:
                    page_no = 1
                
                # Ensure page number is valid
                page_no = max(1, min(page_no, len(doc.pages)))
                
                # Initialize page list if needed
                if page_no not in elements_by_page:
                    elements_by_page[page_no] = []
                
                # Add element to the appropriate page
                elements_by_page[page_no].append({
                    'element': element,
                    'level': level,
                    'type': type(element).__name__
                })
            
            logger.info("Grouped elements across %d pages", len(elements_by_page))
            
            # Create content for each page
            for page_num in range(1, len(doc.pages) + 1):
                page_elements = elements_by_page.get(page_num, [])
                
                # Extract text content for this page by converting page elements to markdown
                page_content_parts = []
                
                for elem_info in page_elements:
                    element = elem_info['element']
                    
                    # Extract text content from different element types
                    if hasattr(element, 'text') and element.text:
                        # Text elements (paragraphs, headings, etc.)
                        text = element.text.strip()
                        if text:
                            page_content_parts.append(text)
                    
                    elif hasattr(element, 'export_to_markdown'):
                        # Elements that can export themselves to markdown
                        try:
                            markdown = element.export_to_markdown()
                            if markdown and markdown.strip():
                                page_content_parts.append(markdown.strip())
                        except Exception as e:
                            logger.debug("Failed to export element to markdown: %s", e)
                    
                    # Note: We don't add image/table elements here as text - 
                    # they will be handled as assets with placeholders
                
                # Combine page content
                page_markdown = '\n\n'.join(page_content_parts)
                
                # If page is empty, create minimal content
                if not page_markdown or not page_markdown.strip():
                    page_markdown = f"# Page {page_num}\n\n[This page contains primarily visual content or is blank]"
                
                # Clean up markdown
                page_markdown = re.sub(r'\n{3,}', '\n\n', page_markdown.strip())
                
                # Find assets that belong specifically to THIS page
                page_assets = []
                for asset in assets:
                    if asset.page_number == page_num:
                        page_assets.append(asset)
                
                # Generate page-specific markdown with asset placeholders
                page_markdown_with_assets = self._generate_page_markdown_with_placeholders(
                    page_markdown, page_assets, page_num
                )
                
                # Create page content object
                page_content = PageContent(
                    page_number=page_num,
                    markdown_content=page_markdown_with_assets,
                    assets=page_assets,
                    metadata={
                        "extracted_at": datetime.utcnow().isoformat(),
                        "asset_count": len(page_assets),
                        "text_length": len(page_markdown_with_assets),
                        "element_count": len(page_elements),
                        "extraction_method": "docling_structured"
                    }
                )
                
                pages_content.append(page_content)
                
                logger.debug(
                    "Page %d: %d elements, %d assets, %d chars content", 
                    page_num, len(page_elements), len(page_assets), len(page_markdown_with_assets)
                )
            
            logger.info("Successfully extracted structured content for %d pages", len(pages_content))
            
        except Exception as e:
            logger.error("Error extracting page contents: %s", e)
            # Fallback: if structured extraction fails, use document-level content
            logger.warning("Falling back to document-level content extraction")
            
            # Create a single page with all content
            full_markdown = doc.export_to_markdown()
            fallback_page = PageContent(
                page_number=1,
                markdown_content=full_markdown,
                assets=assets,
                metadata={
                    "extracted_at": datetime.utcnow().isoformat(),
                    "asset_count": len(assets),
                    "text_length": len(full_markdown),
                    "extraction_method": "fallback_document_level",
                    "fallback_reason": str(e)
                }
            )
            pages_content = [fallback_page]
        
        return pages_content

    # New page-based processing methods for citation support
    async def extract_content_by_pages(self, pdf_path: str) -> List[PageContent]:
        """
        Extract content organized by pages for citation-aware chunking.
        
        Args:
            pdf_path: Path to the PDF file to process
            
        Returns:
            List[PageContent]: Content organized by page with metadata
        """
        try:
            logger.info(f"Starting page-based extraction for {pdf_path}")
            
            # Parse document with Docling
            conv_result = self.doc_converter.convert(pdf_path)
            doc = conv_result.document
            
            # Extract and filter assets
            logger.info("Extracting and filtering assets...")
            result = self._parse_pdf_with_docling(Path(pdf_path), pdf_path)
            all_assets = result.assets
            logger.info(f"Found {len(all_assets)} meaningful assets after filtering")
            
            # Group assets by page
            assets_by_page = self._group_assets_by_page(all_assets, doc)
            
            # Extract content for each page
            pages_content = []
            for page_num in range(1, len(doc.pages) + 1):
                try:
                    page_content = self._extract_page_content(
                        doc, page_num, assets_by_page.get(page_num, [])
                    )
                    if page_content.markdown_content.strip():  # Only add non-empty pages
                        pages_content.append(page_content)
                        logger.debug(f"Extracted content from page {page_num} with {len(page_content.assets)} assets")
                
                except Exception as e:
                    logger.warning(f"Failed to extract content from page {page_num}: {e}")
                    continue
            
            logger.info(f"Successfully extracted content from {len(pages_content)} pages")
            return pages_content
            
        except Exception as e:
            logger.error(f"Failed to extract page-based content from {pdf_path}: {e}")
            raise
    
    def _group_assets_by_page(self, assets: List[AssetInfo], doc) -> Dict[int, List[AssetInfo]]:
        """Group assets by their page number."""
        assets_by_page = {}
        
        for asset in assets:
            page_num = asset.page_number
            if page_num not in assets_by_page:
                assets_by_page[page_num] = []
            assets_by_page[page_num].append(asset)
        
        return assets_by_page
    
    def _extract_page_content(self, doc, page_num: int, page_assets: List[AssetInfo]) -> PageContent:
        """
        Extract content for a specific page using Docling's structured document model.
        
        This method extracts content that actually belongs to the specified page,
        not just a portion of the full document.
        """
        try:
            logger.debug("Extracting structured content for page %d", page_num)
            
            # Collect elements that belong to this specific page
            page_elements = []
            
            for element, level in doc.iterate_items():
                # Get the page number for this element
                element_page_no = getattr(element, 'page_no', None)
                
                # If page_no is not available, try to get it from provenance
                if element_page_no is None and hasattr(element, 'prov') and element.prov:
                    prov = element.prov[0] if element.prov else None
                    if prov and hasattr(prov, 'page_no'):
                        element_page_no = prov.page_no
                    # Also try to infer from bbox coordinates
                    elif prov and hasattr(prov, 'bbox'):
                        bbox = {
                            'left': prov.bbox.l,
                            'top': prov.bbox.t, 
                            'right': prov.bbox.r,
                            'bottom': prov.bbox.b
                        }
                        # Infer page from bbox coordinates if we have multiple pages
                        if hasattr(doc, 'pages') and len(doc.pages) > 1:
                            element_page_no = self._infer_page_from_bbox(bbox, doc)
                
                # Default to page 1 if we can't determine the page
                if element_page_no is None:
                    element_page_no = 1
                
                # Only include elements that belong to this page
                if element_page_no == page_num:
                    page_elements.append({
                        'element': element,
                        'level': level,
                        'type': type(element).__name__
                    })
            
            # Extract text content from page elements
            page_content_parts = []
            
            for elem_info in page_elements:
                element = elem_info['element']
                
                # Extract text content from different element types
                if hasattr(element, 'text') and element.text:
                    # Text elements (paragraphs, headings, etc.)
                    text = element.text.strip()
                    if text:
                        page_content_parts.append(text)
                
                elif hasattr(element, 'export_to_markdown'):
                    # Elements that can export themselves to markdown
                    try:
                        markdown = element.export_to_markdown()
                        if markdown and markdown.strip():
                            page_content_parts.append(markdown.strip())
                    except Exception as e:
                        logger.debug("Failed to export element to markdown: %s", e)
            
            # Combine content for this page
            page_text = '\n\n'.join(page_content_parts)
            
            # If page is empty, create minimal content
            if not page_text or not page_text.strip():
                page_text = f"# Page {page_num}\n\n[This page contains primarily visual content or is blank]"
            
            # Clean up the text
            page_text = re.sub(r'\n{3,}', '\n\n', page_text.strip())
            
            # Generate page-specific markdown with asset placeholders
            page_markdown = self._generate_page_markdown_with_placeholders(
                page_text, page_assets, page_num
            )
            
            # Create page metadata
            page_metadata = {
                'page_number': page_num,
                'asset_count': len(page_assets),
                'total_pages': len(doc.pages),
                'extraction_timestamp': datetime.now().isoformat(),
                'text_length': len(page_text),
                'element_count': len(page_elements),
                'extraction_method': 'docling_structured_single_page'
            }
            
            logger.debug(
                "Page %d extracted: %d elements, %d assets, %d chars", 
                page_num, len(page_elements), len(page_assets), len(page_markdown)
            )
            
            return PageContent(
                page_number=page_num,
                markdown_content=page_markdown,
                assets=page_assets,
                metadata=page_metadata
            )
            
        except Exception as e:
            logger.error(f"Failed to extract structured content for page {page_num}: {e}")
            
            # Fallback: create minimal page content
            fallback_content = f"# Page {page_num}\n\n[Content extraction failed: {str(e)}]"
            
            if page_assets:
                # Add asset placeholders even if content extraction failed
                asset_placeholders = []
                for asset in page_assets:
                    placeholder = f"{{{{ASSET:{asset.asset_id}}}}}"
                    asset_placeholders.append(placeholder)
                fallback_content = "\n\n".join(asset_placeholders) + "\n\n" + fallback_content
            
            return PageContent(
                page_number=page_num,
                markdown_content=fallback_content,
                assets=page_assets,
                metadata={
                    'page_number': page_num,
                    'asset_count': len(page_assets),
                    'total_pages': len(doc.pages),
                    'extraction_timestamp': datetime.now().isoformat(),
                    'text_length': len(fallback_content),
                    'extraction_method': 'fallback_minimal',
                    'error': str(e)
                }
            )
    
    def _generate_page_markdown_with_placeholders(self, page_text: str, page_assets: List[AssetInfo], page_num: int) -> str:
        """Generate markdown for a specific page with asset placeholders."""
        processed_content = page_text
        
        # Sort assets by reading order for this page
        sorted_assets = sorted(page_assets, key=lambda a: (
            -a.bbox['top'] if a.bbox else 0,  # Top to bottom (negative for top-first)
            a.bbox['left'] if a.bbox else 0   # Left to right
        ))
        
        # Insert asset placeholders at the beginning for now
        # In a more sophisticated implementation, you'd analyze the text layout
        # to determine where each asset should be placed
        asset_placeholders = []
        for asset in sorted_assets:
            placeholder = f"{{{{ASSET:{asset.asset_id}}}}}"
            asset_placeholders.append(placeholder)
        
        if asset_placeholders:
            # Add placeholders at the top of the page content
            placeholders_text = "\n\n".join(asset_placeholders) + "\n\n"
            processed_content = placeholders_text + processed_content
        
        return processed_content

    def _infer_page_from_bbox(self, bbox: Dict[str, float], doc) -> int:
        """
        Infer page number from bbox coordinates by comparing with page boundaries.
        
        This is a best-effort approach for cases where Docling doesn't provide
        explicit page numbers for elements.
        
        Args:
            bbox: Bounding box with 'left', 'top', 'right', 'bottom' coordinates
            doc: Docling document object with pages
            
        Returns:
            int: Inferred page number (1-indexed)
        """
        if not bbox or not hasattr(doc, 'pages') or len(doc.pages) <= 1:
            return 1
            
        try:
            # Get the vertical position of the element
            element_top = bbox['top']
            element_bottom = bbox['bottom']
            element_center_y = (element_top + element_bottom) / 2
            
            # For multi-page documents, we'll use a simple heuristic:
            # If the document has N pages and the element's y-coordinate suggests
            # it's beyond the first page's typical height, assign it to later pages
            
            num_pages = len(doc.pages)
            
            # Get representative page dimensions
            page_height = 800  # Default fallback
            if hasattr(doc.pages[0], 'size') and doc.pages[0].size:
                if hasattr(doc.pages[0].size, 'height'):
                    page_height = doc.pages[0].size.height
            
            # Simple heuristic: distribute elements based on relative position
            # This assumes elements are laid out in reading order vertically
            if element_center_y > page_height * 0.9:  # Element is likely on a subsequent page
                # For a 2-page document, if element is significantly below typical page height,
                # it's probably on page 2
                if num_pages >= 2:
                    # Rough estimation: if y > 1.5 * page_height, it's likely page 2+
                    estimated_page = min(2 + int((element_center_y - page_height) / page_height), num_pages)
                    logger.debug(
                        "Bbox inference: element_y=%.0f, page_height=%.0f, estimated_page=%d", 
                        element_center_y, page_height, estimated_page
                    )
                    return estimated_page
            
            # Default to page 1 if heuristics don't suggest otherwise
            return 1
            
        except Exception as e:
            logger.warning("Failed to infer page from bbox: %s", e)
            return 1  # Safe fallback
