"""
PDF ingestor.

Responsibilities
----------------
1. Enumerate documents that live under an S3 prefix.
2. Download them to a local temp dir.
3. Extract text and inline images page-by-page.
4. Return a list of `IngestedDoc` instances that the rest of the
   ingestion pipeline (vision captioner → doc_builder → vector-store)
   can consume.
"""

from __future__ import annotations

import asyncio
import io
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence

import boto3
import fitz  # PyMuPDF
from PIL import Image


# Data model                                                                   
@dataclass
class IngestedDoc:
    """Raw output of the ingestor – ready for the Vision step."""
    s3_key: str                   # Full S3 key (for traceability)
    text: str                     # All text concatenated
    images: List[bytes] = field(default_factory=list)   # PNG bytes

# Main class
class S3PDFIngestor:
    """Pull PDFs from an S3 bucket and extract text/images.
    This class handles downloading PDFs from S3, extracting text and images,
    and returning structured data for further processing.
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
    ) -> None:
        if not bucket:
            raise ValueError("`bucket` must be a non-empty string")

        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.s3 = boto3.client("s3")
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.tmp_root = Path(tmp_dir or tempfile.gettempdir()) / "jarvis_ingest"
        self.tmp_root.mkdir(exist_ok=True)

    # public API
    async def process_all(self) -> List[IngestedDoc]:
        """Download every PDF under the prefix and return parsed docs."""
        keys = self._list_keys(".pdf")
        coros = [self._process_single(k) for k in keys]
        return await asyncio.gather(*coros)
    
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
                # Debugging output to trace keys
                print("DEBUG key ->", obj["Key"])
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.lower().endswith(suffix):
                    keys.append(key)
        return keys

    async def _process_single(self, key: str) -> IngestedDoc:
        """Download → parse → return a single document."""
        async with self.semaphore:
            local_path = await asyncio.to_thread(self._download_to_tmp, key)
            try:
                text, images = await asyncio.to_thread(self._parse_pdf, local_path)
            finally:
                local_path.unlink(missing_ok=True)

        return IngestedDoc(s3_key=key, text=text, images=images)

    # parsing helpers

    def _download_to_tmp(self, key: str) -> Path:
        """Blocking S3 download (run in thread-pool)."""
        local = self.tmp_root / Path(key).name
        self.s3.download_file(self.bucket, key, str(local))
        return local

    def _parse_pdf(self, path: Path) -> tuple[str, list[bytes]]:
        """Extract all text and images using PyMuPDF."""
        doc = fitz.open(path)
        text_parts: list[str] = []
        images: list[bytes] = []

        for page in doc:
            text_parts.append(page.get_text("text"))

            # Extract inline images
            for img_index, img in enumerate(page.get_images(full=True)):
                xref = img[0]
                base = doc.extract_image(xref)
                pix = Image.open(io.BytesIO(base["image"]))
                # Down-scale large pages to keep token count sane
                pix.thumbnail((1024, 1024))
                buf = io.BytesIO()
                pix.save(buf, format="PNG", optimize=True)
                images.append(buf.getvalue())

        doc.close()
        return "\n".join(text_parts).strip(), images
    
    