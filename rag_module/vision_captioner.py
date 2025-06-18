"""
Batch-wise image captioning using OpenAI vision models.

Why we needed a rewrite
----------------------
* The new openai>=1.0 client moved `.ChatCompletion` → `.chat.completions`.
* Our previous implementation streamed **all** images in a single request,
  blowing past the per-minute *and* per-request token caps.

This version:
* Sends at most `IMAGES_PER_REQUEST` pictures per call.
* Does a cheap JPEG → PNG conversion & thumbnail so each base64 string is tiny.
* Retries with exponential back-off on HTTP 429s.
"""

from __future__ import annotations

import asyncio
import base64
import io
from dataclasses import dataclass
from typing import List
from openai import AsyncOpenAI
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_random_exponential

import openai

IMAGES_PER_REQUEST = 4                 # keep prompts < 3 k tokens
MODEL = "gpt-4o-2024-08-06"
SYSTEM_PROMPT = (
    "You are a concise alt-text generator. "
    "Describe each image in one factual sentence."
)

# Data model                                                                
@dataclass
class CaptionResult:
    image_index: int
    caption: str

# Main class
class VisionCaptioner:
    def __init__(self, api_key: str, *, images_per_request: int = IMAGES_PER_REQUEST):
        self.client = AsyncOpenAI(api_key = api_key)
        self.images_per_request = images_per_request

    # public

    async def caption_images(self, images: List[bytes]) -> List[str]:
        """Return one caption per `images` item, in the same order."""
        if not images:
            return []

        batches = [
            images[i : i + self.images_per_request]
            for i in range(0, len(images), self.images_per_request)
        ]

        # Fire the batches concurrently but not *too* fast.
        sem = asyncio.Semaphore(3)
        results: list[CaptionResult] = []

        async def _worker(batch: List[bytes], offset: int):
            async with sem:
                captions = await self._call_openai(batch)
                for idx, caption in enumerate(captions):
                    results.append(CaptionResult(offset + idx, caption))

        await asyncio.gather(
            *(_worker(batch, i * self.images_per_request) for i, batch in enumerate(batches))
        )

        # Re-order because batches resolve out-of-order
        return [c.caption for c in sorted(results, key=lambda x: x.image_index)]

    # internals
    @retry(
        reraise=True,
        wait=wait_random_exponential(multiplier=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def _call_openai(self, imgs: List[bytes]) -> List[str]:
        """One OpenAI request with up to `images_per_request` pictures."""
        content_blocks = []
        for img in imgs:
            data_url = self._bytes_to_data_url(img)
            content_blocks.append({"type": "image_url", "image_url": {"url": data_url}})

        resp = await self.client.chat.completions.create(
            model=MODEL,
            temperature=0.2,
            max_tokens=120 * len(imgs),   # generous but safe
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content_blocks},
            ],
        )
        text = resp.choices[0].message.content
        # One caption per line → robust even if model gets creative
        return [line.strip() for line in text.splitlines() if line.strip()]

    # helpers
    @staticmethod
    def _bytes_to_data_url(raw: bytes) -> str:
        """Resize → encode → return data-url."""
        img = Image.open(io.BytesIO(raw))
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"