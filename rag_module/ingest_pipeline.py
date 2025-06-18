"""
Run *offline*  ➜  python -m rag_module.ingest_pipeline \
    --bucket my-bucket --prefix raw-notes --index notes-prod
This script can be use to parse all PDFs under a given S3 bucket/prefix,
extract text and images, caption the images, and build a vector store index.
The purpose of it is to use it to check when changes are made and we want to update all the already parsed PDFs.
Or run CLI locally for smoke testing.
"""
from __future__ import annotations
import argparse, asyncio, logging

from rag_module.pdfingestor import S3PDFIngestor
from rag_module.vision_captioner import VisionCaptioner
from rag_module.doc_builder import DocBuilder
from settings import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def ingest_pipeline(bucket: str, prefix: str, *, index_name: str) -> None:
    # extract text + thumbnails
    ingestor = S3PDFIngestor(bucket=bucket, prefix=prefix)
    docs     = await ingestor.process_all()

    if not docs:
        logger.info("No PDFs to ingest under s3://%s/%s", bucket, prefix)
        return

    # caption thumbnails (uses presigned URLs under the hood)
    captioner = VisionCaptioner(api_key=settings.openai_api_key)

    for doc in docs:
        captions = await captioner.caption_images(doc.images)
        # chunk + embed + upsert
        builder = DocBuilder(index_name=index_name)
        builder.build(doc, captions)

    logger.info("Ingest complete: %d documents processed", len(docs))


# CLI
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--prefix", required=True)
    p.add_argument("--index",  required=True)
    args = p.parse_args()
    asyncio.run(ingest_pipeline(args.bucket, args.prefix, index_name=args.index))