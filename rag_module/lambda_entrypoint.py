"""
lambda_entrypoint.py
────────────────────
AWS Lambda handler for “ObjectCreated” S3 events.
Process ONE or more newly-uploaded PDFs and push them to the
tenant’s Pinecone index.

Assumptions
-----------
• Every tenant in tenants.json defines:
      s3_bucket
      s3_raw_docs_prefix   (unique within the bucket)
      index_rag
• The triggering S3 object’s bucket *and* key prefix uniquely
  identify which tenant owns the file.
• Only PDFs are ingested. Non-PDF uploads are ignored.

Environment variables
---------------------
OPENAI_API_KEY      – required by VisionCaptioner
PINECONE_API_KEY    – used in utils.vector_store.get_vector_store
AWS_REGION          – defaults to "ca-central-1"
"""

from __future__ import annotations
import asyncio
import urllib.parse
import json
import time
import traceback
import gc
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from rag_module.pdfingestor import S3PDFIngestor
from rag_module.vision_captioner import VisionCaptioner
from rag_module.doc_builder import DocBuilder
from settings_ingest import settings
from utils.logging_config import logger

# Enhanced monitoring imports
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available - memory monitoring disabled")

try:
    import boto3
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger.warning("boto3 not available - CloudWatch metrics disabled")

# Configuration constants for reliability
MAX_FILE_SIZE_MB = 100  # Maximum file size to process
MAX_MEMORY_USAGE_PERCENT = 85  # Alert when memory usage exceeds this
MIN_TIME_REMAINING_MS = 120000  # Minimum time needed to process a document (2 minutes)
MEMORY_CHECK_INTERVAL = 5  # Seconds between memory checks during processing

# Memory monitoring class
class MemoryMonitor:
    """Monitor memory usage and provide alerts."""
    
    def __init__(self, context=None):
        self.context = context
        self.initial_memory = self.get_memory_usage()
        self.peak_memory = self.initial_memory
        
    def get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        if PSUTIL_AVAILABLE:
            return psutil.Process().memory_info().rss / 1024 / 1024
        return 0.0
    
    def get_memory_percent(self) -> float:
        """Get memory usage as percentage of available."""
        if not self.context or not PSUTIL_AVAILABLE:
            return 0.0
        current = self.get_memory_usage()
        # Convert memory_limit_in_mb to float to handle string values from Lambda context
        try:
            memory_limit = float(self.context.memory_limit_in_mb)
        except (ValueError, AttributeError, TypeError):
            # Fallback to a reasonable default if memory limit is not available
            memory_limit = 512.0  # Default Lambda memory limit
            logger.warning("Could not get memory limit from context, using default 512MB")
        return (current / memory_limit) * 100
    
    def check_memory_safety(self) -> Tuple[bool, str]:
        """Check if memory usage is safe to continue processing."""
        current_mb = self.get_memory_usage()
        self.peak_memory = max(self.peak_memory, current_mb)
        
        if not self.context:
            return True, f"Memory: {current_mb:.1f}MB"
            
        percent = self.get_memory_percent()
        
        if percent > MAX_MEMORY_USAGE_PERCENT:
            return False, f"Memory usage too high: {current_mb:.1f}MB ({percent:.1f}%)"
        
        return True, f"Memory: {current_mb:.1f}MB ({percent:.1f}%)"
    
    def get_summary(self) -> Dict[str, float]:
        """Get memory usage summary."""
        current = self.get_memory_usage()
        return {
            'initial_mb': self.initial_memory,
            'current_mb': current,
            'peak_mb': self.peak_memory,
            'percent_used': self.get_memory_percent()
        }

# Configure temp directory for Lambda environment at module load time
import os
if (os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or 
    os.environ.get('LAMBDA_RUNTIME_DIR') or 
    os.environ.get('LAMBDA_TASK_ROOT')):
    # Set all temp and cache directories to /tmp
    os.environ['TMPDIR'] = '/tmp'
    os.environ['TMP'] = '/tmp'
    os.environ['TEMP'] = '/tmp'
    os.environ['HOME'] = '/tmp'
    os.environ['TRANSFORMERS_CACHE'] = '/tmp/.cache/huggingface'
    os.environ['HF_HOME'] = '/tmp/.cache/huggingface'
    os.environ['XDG_CACHE_HOME'] = '/tmp/.cache'
    os.environ['TORCH_HOME'] = '/tmp/.cache/torch'
    os.environ['NUMBA_CACHE_DIR'] = '/tmp/.cache/numba'
    
    import tempfile
    tempfile.tempdir = '/tmp'
    logger.info("Lambda environment detected at module load, configured temp directory and cache paths to /tmp")


_raw = json.loads(Path("/opt/app/tenants.json").read_text())

# Always end up with a list[dict]
TENANT_CONFIGS: list[dict]
if isinstance(_raw, dict):          # JSON was an object keyed by guild_id
    TENANT_CONFIGS = list(_raw.values())
elif isinstance(_raw, list):        # JSON already a list
    TENANT_CONFIGS = _raw
else:
    TENANT_CONFIGS = []             # fallback, shouldn't happen

# captioner with enhanced capabilities
captioner = VisionCaptioner(api_key=settings.openai_api_key)

logger.info("Lambda initialized with %d tenant configs", len(TENANT_CONFIGS))

# Helper: find tenant by bucket + prefix                                    
def _resolve_tenant(bucket: str, key: str):

    for t in TENANT_CONFIGS:              # t is guaranteed to be a dict
        if t["s3_bucket"] == bucket and key.startswith(t["s3_raw_docs_prefix"]):
            return t
    return None


# Helper functions for enhanced processing
async def _get_file_size(bucket: str, key: str) -> float:
    """Get file size in MB from S3."""
    try:
        if BOTO3_AVAILABLE:
            s3_client = boto3.client('s3')
            response = s3_client.head_object(Bucket=bucket, Key=key)
            size_bytes = response['ContentLength']
            return size_bytes / (1024 * 1024)  # Convert to MB
        else:
            logger.warning("boto3 not available - cannot check file size for %s", key)
            return 0.0
    except Exception as e:
        logger.warning("Failed to get file size for %s: %s", key, str(e))
        return 0.0

async def _process_with_docling(bucket: str, key: str, tenant: dict, tmp_dir: str, monitor: MemoryMonitor, context) -> Dict[str, Any]:
    """Process PDF using Docling with memory monitoring."""
    result = {'chunks_created': 0, 'assets_processed': 0, 'success': False}
    
    try:
        ingestor = S3PDFIngestor(
            bucket=bucket,
            prefix=tenant['s3_raw_docs_prefix'],
            tmp_dir=tmp_dir
        )

        # Periodic memory checks during processing
        if monitor:
            safe, status = monitor.check_memory_safety()
            if not safe:
                raise RuntimeError(f"Memory safety check failed: {status}")

        # Parse document with Docling
        doc = await ingestor.process_key(key)
        
        # Check memory after parsing
        if monitor:
            safe, status = monitor.check_memory_safety()
            if not safe:
                logger.warning("High memory usage after parsing %s: %s", key, status)

        # Use enhanced asset captioning if available
        if hasattr(doc, 'assets') and doc.assets:
            logger.info("Found %d assets in %s", len(doc.assets), key)
            
            # Check time and memory before captioning
            if context:
                remaining_time = context.get_remaining_time_in_millis()
                if remaining_time < MIN_TIME_REMAINING_MS:
                    raise RuntimeError(f"Insufficient time for asset processing: {remaining_time/1000:.1f}s")
            
            asset_captions = await captioner.caption_assets(doc.assets)
            result['assets_processed'] = len(doc.assets)
            
            # Build with enhanced pipeline
            builder = DocBuilder(index_name=tenant['index_rag'])
            n_chunks = builder.build_with_assets(doc, asset_captions)
            result['chunks_created'] = n_chunks
            
            logger.info(
                "✓ %s → %d chunks, %d assets → %s", 
                key, n_chunks, len(doc.assets), tenant['index_rag']
            )
        else:
            # Fallback to legacy processing if needed
            logger.info("No assets found in %s, using legacy processing", key)
            
            # Extract images for legacy interface
            images = getattr(doc, 'images', [])
            captions = await captioner.caption_images(images)
            
            # Build with legacy interface
            builder = DocBuilder(index_name=tenant['index_rag'])
            n_chunks = builder.build(doc, captions)
            result['chunks_created'] = n_chunks
            
            logger.info("✓ %s → %d chunks (legacy) → %s", key, n_chunks, tenant['index_rag'])
        
        result['success'] = True
        return result
        
    except Exception as e:
        logger.error("Docling processing failed for %s: %s", key, str(e))
        raise

async def _process_with_fallback(bucket: str, key: str, tenant: dict, tmp_dir: str) -> Dict[str, Any]:
    """Fallback processing using simpler PDF parsing when Docling fails."""
    result = {'chunks_created': 0, 'assets_processed': 0, 'success': False}
    
    try:
        logger.info("Using fallback processing for %s", key)
        
        # Import fallback libraries
        try:
            import PyPDF2
            import io
            import boto3
        except ImportError as e:
            logger.error("Fallback libraries not available: %s", str(e))
            raise RuntimeError(f"Fallback processing not available: {str(e)}")
        
        # Download and process with simple text extraction
        s3_client = boto3.client('s3')
        
        # Download file
        response = s3_client.get_object(Bucket=bucket, Key=key)
        pdf_content = response['Body'].read()
        
        # Extract text using PyPDF2
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
        text_content = ""
        
        for page in pdf_reader.pages:
            try:
                text_content += page.extract_text() + "\n"
            except Exception as e:
                logger.warning("Failed to extract text from page: %s", str(e))
                continue
        
        if not text_content.strip():
            raise RuntimeError("No text content extracted from PDF")
        
        # Create a simple document structure for fallback processing
        from rag_module.doc_builder import DocBuilder
        
        # Build chunks without assets
        builder = DocBuilder(index_name=tenant['index_rag'])
        
        # Create a minimal document-like object
        class FallbackDoc:
            def __init__(self, text: str, source: str):
                self.text = text
                self.source = source
                self.metadata = {'source': source, 'fallback': True}
        
        fallback_doc = FallbackDoc(text_content, key)
        
        # Use simpler chunking strategy
        n_chunks = builder.build_simple_text(fallback_doc)
        result['chunks_created'] = n_chunks
        result['success'] = True
        
        logger.info("✓ %s → %d chunks (fallback) → %s", key, n_chunks, tenant['index_rag'])
        return result
        
    except Exception as e:
        logger.error("Fallback processing also failed for %s: %s", key, str(e))
        raise


# Enhanced async processing for ONE object key
async def _process_object(bucket: str, key: str, tenant, context=None, monitor: MemoryMonitor = None) -> Dict[str, Any]:
    """Process a single PDF using the enhanced Docling pipeline with comprehensive safety checks."""
    
    start_time = time.time()
    processing_result = {
        'success': False,
        'key': key,
        'chunks_created': 0,
        'assets_processed': 0,
        'processing_time_s': 0,
        'memory_used_mb': 0,
        'error': None,
        'fallback_used': False
    }
    
    try:
        if not key.lower().endswith(".pdf"):
            logger.info("Skipping non-PDF upload: %s", key)
            processing_result['success'] = True
            processing_result['error'] = 'Not a PDF file'
            return processing_result

        # Get file size and validate
        file_size_mb = await _get_file_size(bucket, key)
        if file_size_mb > MAX_FILE_SIZE_MB:
            logger.warning("File too large: %s (%.1fMB) - max allowed: %dMB", key, file_size_mb, MAX_FILE_SIZE_MB)
            processing_result['error'] = f'File too large: {file_size_mb:.1f}MB'
            return processing_result

        # Check remaining time
        if context:
            remaining_time = context.get_remaining_time_in_millis()
            if remaining_time < MIN_TIME_REMAINING_MS:
                logger.warning("Insufficient time remaining: %.1fs for %s", remaining_time/1000, key)
                processing_result['error'] = f'Insufficient time: {remaining_time/1000:.1f}s remaining'
                return processing_result

        # Memory safety check
        if monitor:
            safe, memory_status = monitor.check_memory_safety()
            if not safe:
                logger.warning("Memory usage too high before processing %s: %s", key, memory_status)
                processing_result['error'] = f'High memory usage: {memory_status}'
                return processing_result

        logger.info("Processing %s (%.1fMB) with enhanced pipeline", key, file_size_mb)
        
        # Ensure we use /tmp in Lambda environment
        import os
        tmp_dir = None
        if (os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or 
            os.environ.get('LAMBDA_RUNTIME_DIR') or 
            os.environ.get('LAMBDA_TASK_ROOT')):
            tmp_dir = '/tmp'
            logger.info("Lambda environment detected, explicitly using /tmp for PDF processing")

        try:
            # Try primary processing with Docling
            success_result = await _process_with_docling(bucket, key, tenant, tmp_dir, monitor, context)
            processing_result.update(success_result)
            processing_result['success'] = True
            
        except (MemoryError, RuntimeError) as e:
            logger.warning("Docling processing failed for %s: %s - trying fallback", key, str(e))
            
            # Force garbage collection before fallback
            gc.collect()
            
            # Try fallback processing
            fallback_result = await _process_with_fallback(bucket, key, tenant, tmp_dir)
            processing_result.update(fallback_result)
            processing_result['fallback_used'] = True
            processing_result['success'] = fallback_result.get('success', False)
            
        except Exception as e:
            logger.error("All processing methods failed for %s: %s", key, str(e))
            processing_result['error'] = str(e)
            raise
            
    except Exception as e:
        logger.error("Failed to process %s: %s", key, str(e))
        logger.error("Traceback: %s", traceback.format_exc())
        processing_result['error'] = str(e)
        
    finally:
        processing_result['processing_time_s'] = time.time() - start_time
        if monitor:
            memory_summary = monitor.get_summary()
            processing_result['memory_used_mb'] = memory_summary['peak_mb']
            
        logger.info("Processing completed for %s: success=%s, time=%.1fs, memory=%.1fMB", 
                   key, processing_result['success'], 
                   processing_result['processing_time_s'],
                   processing_result['memory_used_mb'])
    
    return processing_result


# Enhanced Lambda entrypoint
def handler(event, context):
    """
    Handle S3 ObjectCreated events with enhanced error handling and monitoring.
    """
    
    # Initialize monitoring
    monitor = MemoryMonitor(context) if PSUTIL_AVAILABLE else None
    start_time = time.time()
    
    # Log initial state
    logger.info("Lambda invocation started")
    if monitor:
        # Convert memory_limit_in_mb to float to handle string values from Lambda context
        try:
            memory_limit = float(context.memory_limit_in_mb) if context else 512.0
        except (ValueError, AttributeError, TypeError):
            memory_limit = 512.0  # Default Lambda memory limit
        logger.info("Initial memory: %.1fMB (%.1f%% of %.1fMB limit)", 
                   monitor.initial_memory, monitor.get_memory_percent(), 
                   memory_limit)
    
    if context:
        logger.info("Timeout: %.1fs, Remaining: %.1fs", 
                   context.get_remaining_time_in_millis() / 1000,
                   context.get_remaining_time_in_millis() / 1000)
    
    try:
        # Force all temporary operations to use /tmp in Lambda environment
        import os
        if (os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or 
            os.environ.get('LAMBDA_RUNTIME_DIR') or 
            os.environ.get('LAMBDA_TASK_ROOT')):
            # Set all temp and cache directories to /tmp
            os.environ['TMPDIR'] = '/tmp'
            os.environ['TMP'] = '/tmp'
            os.environ['TEMP'] = '/tmp'
            os.environ['HOME'] = '/tmp'
            os.environ['TRANSFORMERS_CACHE'] = '/tmp/.cache/huggingface'
            os.environ['HF_HOME'] = '/tmp/.cache/huggingface'
            os.environ['XDG_CACHE_HOME'] = '/tmp/.cache'
            os.environ['TORCH_HOME'] = '/tmp/.cache/torch'
            os.environ['NUMBA_CACHE_DIR'] = '/tmp/.cache/numba'
            
            # Also override tempfile module's temp directory
            import tempfile
            tempfile.tempdir = '/tmp'
            logger.info("Lambda environment detected, forced all temp and cache operations to use /tmp")
        
        # Validate event structure
        if "Records" not in event:
            error_msg = f"Malformed event - missing Records: {event}"
            logger.error(error_msg)
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "status": "error", 
                    "processed": 0, 
                    "message": "Malformed event",
                    "error": error_msg
                })
            }

        # Process records with enhanced error handling
        tasks = []
        skipped_records = 0
        
        for rec in event["Records"]:
            try:
                if not rec.get("eventName", "").startswith("ObjectCreated"):
                    skipped_records += 1
                    continue

                bucket = rec["s3"]["bucket"]["name"]
                raw_key = rec["s3"]["object"]["key"]
                key = urllib.parse.unquote_plus(raw_key)
                tenant = _resolve_tenant(bucket, key)

                if tenant:
                    logger.info("Queuing %s for tenant %s", key, tenant.get('name', 'unknown'))
                    tasks.append(_process_object(bucket, key, tenant, context, monitor))
                else:
                    logger.warning("No tenant found for s3://%s/%s", bucket, key)
                    skipped_records += 1
                    
            except Exception as e:
                logger.error("Failed to process record %s: %s", rec, str(e))
                skipped_records += 1

        if not tasks:
            logger.info("No valid PDF uploads found in event (skipped: %d)", skipped_records)
            return _create_success_response(0, 0, skipped_records, monitor, start_time)

        # Execute processing with comprehensive error handling
        async def _drive():
            return await _execute_processing_tasks(tasks, monitor, start_time, skipped_records, context)
        
        try:
            return asyncio.run(_drive())
        except Exception as e:
            logger.error("Async execution failed: %s", str(e))
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "status": "async_error",
                    "processed": 0,
                    "message": "Async execution failed",
                    "error": str(e),
                    "execution_time_s": time.time() - start_time
                })
            }
        
    except Exception as e:
        logger.error("Handler execution failed: %s", str(e))
        logger.error("Traceback: %s", traceback.format_exc())
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "processed": 0,
                "message": "Handler execution failed",
                "error": str(e),
                "execution_time_s": time.time() - start_time
            })
        }


async def _execute_processing_tasks(tasks, monitor: MemoryMonitor, start_time: float, skipped_records: int, context) -> Dict[str, Any]:
    """Execute processing tasks with comprehensive error handling."""
    
    try:
        logger.info("Processing %d documents...", len(tasks))
        
        # Run all tasks with error collection
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze results
        successful_results = []
        failed_results = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Task %d failed with exception: %s", i, str(result))
                failed_results.append({
                    'task_index': i,
                    'error': str(result),
                    'success': False
                })
            elif isinstance(result, dict):
                if result.get('success', False):
                    successful_results.append(result)
                else:
                    failed_results.append(result)
            else:
                logger.warning("Unexpected result type for task %d: %s", i, type(result))
                failed_results.append({
                    'task_index': i,
                    'error': f'Unexpected result type: {type(result)}',
                    'success': False
                })
        
        # Calculate metrics
        total_chunks = sum(r.get('chunks_created', 0) for r in successful_results)
        total_assets = sum(r.get('assets_processed', 0) for r in successful_results)
        fallback_count = sum(1 for r in successful_results if r.get('fallback_used', False))
        
        success_count = len(successful_results)
        failure_count = len(failed_results)
        
        # Log summary
        logger.info("Processing completed: %d successful, %d failed, %d skipped", 
                   success_count, failure_count, skipped_records)
        
        if failure_count > 0:
            logger.error("Failed documents:")
            for failed in failed_results:
                logger.error("  - %s: %s", failed.get('key', 'unknown'), failed.get('error', 'unknown error'))
        
        # Determine status
        if success_count == len(tasks):
            status = "success"
            status_code = 200
        elif success_count > 0:
            status = "partial_success"
            status_code = 207  # Multi-Status
        else:
            status = "failure"
            status_code = 500
        
        return {
            "statusCode": status_code,
            "body": json.dumps({
                "status": status,
                "processed": success_count,
                "failed": failure_count,
                "skipped": skipped_records,
                "total_chunks_created": total_chunks,
                "total_assets_processed": total_assets,
                "fallback_used_count": fallback_count,
                "execution_time_s": time.time() - start_time,
                "memory_summary": monitor.get_summary() if monitor else None,
                "failed_documents": [f.get('key', f.get('task_index', 'unknown')) for f in failed_results] if failed_results else []
            })
        }
        
    except Exception as e:
        logger.error("Task execution failed: %s", str(e))
        logger.error("Traceback: %s", traceback.format_exc())
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "execution_error",
                "processed": 0,
                "message": "Task execution failed",
                "error": str(e),
                "execution_time_s": time.time() - start_time
            })
        }


def _create_success_response(processed: int, failed: int, skipped: int, monitor: MemoryMonitor, start_time: float) -> Dict[str, Any]:
    """Create a standardized success response."""
    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "success",
            "processed": processed,
            "failed": failed,
            "skipped": skipped,
            "message": "No PDFs to process" if processed == 0 else f"Processed {processed} documents",
            "execution_time_s": time.time() - start_time,
            "memory_summary": monitor.get_summary() if monitor else None
        })
    }

