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
from pathlib import Path
from rag_module.pdfingestor import S3PDFIngestor
from rag_module.vision_captioner import VisionCaptioner
from rag_module.doc_builder import DocBuilder
from settings_ingest import settings
from utils.logging_config import logger


_raw = json.loads(Path("/opt/app/tenants.json").read_text())

# Always end up with a list[dict]
TENANT_CONFIGS: list[dict]
if isinstance(_raw, dict):          # JSON was an object keyed by guild_id
    TENANT_CONFIGS = list(_raw.values())
elif isinstance(_raw, list):        # JSON already a list
    TENANT_CONFIGS = _raw
else:
    TENANT_CONFIGS = []             # fallback, shouldn't happen

# captioner
captioner  = VisionCaptioner(api_key=settings.openai_api_key)

# Helper: find tenant by bucket + prefix                                    
def _resolve_tenant(bucket: str, key: str):

    for t in TENANT_CONFIGS:              # t is guaranteed to be a dict
        if t["s3_bucket"] == bucket and key.startswith(t["s3_raw_docs_prefix"]):
            return t
    return None


# Async processing for ONE object key
async def _process_object(bucket: str, key: str, tenant) -> None:
    if not key.lower().endswith(".pdf"):
        logger.info("Skipping non-PDF upload: %s", key)
        return

    ingestor = S3PDFIngestor(
        bucket=bucket,
        prefix=tenant['s3_raw_docs_prefix']
    )

    # parse this key
    doc = await ingestor.process_key(key)

    # caption images
    captions = await captioner.caption_images(doc.images)

    # build and upsert chunks
    builder  = DocBuilder(index_name=tenant['index_rag'],)
    n_chunks = builder.build(doc, captions)

    logger.info("✓ %s → %d chunks → %s", key, n_chunks, tenant['index_rag'])


# Lambda entrypoint
def handler(event, _ctx):
    """
    Handle S3 ObjectCreated events.
    """
    if "Records" not in event:
        logger.error("Malformed event: %s", event)
        return {"status": "error", "processed": 0}

    tasks = []
    for rec in event["Records"]:
        if not rec.get("eventName", "").startswith("ObjectCreated"):
            continue

        bucket = rec["s3"]["bucket"]["name"]
        raw_key    = rec["s3"]["object"]["key"]
        key = urllib.parse.unquote_plus(raw_key)
        tenant = _resolve_tenant(bucket, key)

        if tenant:
            tasks.append(_process_object(bucket, key, tenant))

    # ── run all work in a *single* event-loop ──────────────────────────
    if tasks:
        async def _drive():
            await asyncio.gather(*tasks)

        asyncio.run(_drive())          # <-- _drive() is a coroutine

    return {"status": "OK", "processed": len(tasks)}