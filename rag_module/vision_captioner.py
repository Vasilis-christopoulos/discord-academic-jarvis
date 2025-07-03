"""
Detailed image analysis using OpenAI vision models for academic content.

Optimized for comprehensive yet concise visual content analysis
-------------------------------------------------------------
* Focuses on visual elements that require vision understanding (pictures, figures, diagrams)
* Provides detailed descriptions that capture essential information for AI reasoning
* Structured text elements (tables, code, formulas) are processed as text by DocBuilder
* Maintains backward compatibility with existing pipeline
* Uses specialized prompting for different visual content types

This version:
* Analyzes visual content in detail while remaining concise
* Captures specific data points, relationships, and academic context
* Sends at most `IMAGES_PER_REQUEST` pictures per call
* Does JPEG → PNG conversion & thumbnail for efficient processing
* Retries with exponential back-off on HTTP 429s
* Focuses on informational value rather than surface descriptions
"""

from __future__ import annotations

import asyncio
import base64
import io
from dataclasses import dataclass
from typing import List, Dict, Union
from openai import AsyncOpenAI
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_random_exponential

from utils.logging_config import logger

# Try to import AssetInfo from the updated pdfingestor
try:
    from .pdfingestor import AssetInfo
except ImportError:
    # Fallback definition for backward compatibility
    @dataclass
    class AssetInfo:
        asset_id: str
        asset_type: str  
        image_bytes: bytes
        page_number: int
        bbox: Dict[str, float] = None

IMAGES_PER_REQUEST = 4                 # keep prompts < 3 k tokens
MODEL = "gpt-4o-2024-08-06"

# Enhanced system prompts for visual asset types - optimized for detailed yet concise descriptions
SYSTEM_PROMPTS = {
    "picture": (
        "You are a detailed image analyst for academic documents. Provide a comprehensive yet concise description "
        "that captures the essential information an AI would need to understand and reason about this content. "
        "For charts/graphs: specify the type, variables, key trends, and notable data points. "
        "For diagrams: describe the structure, relationships, and key components. "
        "For photos/images: identify subjects, context, and academically relevant details. "
        "For mathematical content: describe the concepts, formulas, or relationships shown. "
        "Use precise, technical language that preserves the informational value. One detailed description per line."
    ),
    "figure": (
        "You are a detailed figure analyst for academic documents. Provide a comprehensive yet concise description "
        "that captures the structure, relationships, and key information shown. "
        "For flowcharts: describe the process flow, decision points, and outcomes. "
        "For diagrams: specify components, connections, and hierarchical relationships. "
        "For illustrations: identify the concept being demonstrated and key elements. "
        "Include specific details about labels, values, categories, or measurements when visible. "
        "Use precise terminology that preserves the academic value. One detailed description per line."
    ),
    "default": (
        "You are a detailed visual analyst for academic documents. Provide a comprehensive yet concise description "
        "that captures all essential information an AI would need to understand this visual content. "
        "Include specific data points, labels, relationships, and context that make this content academically valuable. "
        "For any charts, graphs, or data visualizations, specify the variables, scale, and key insights. "
        "For conceptual visuals, describe the main ideas, components, and their relationships. "
        "Use precise, informative language while remaining concise. One detailed description per line."
    )
}

# Data model                                                                
@dataclass
class CaptionResult:
    asset_id: str          # Asset identifier (for new workflow) or index (for legacy)
    caption: str
    asset_type: str = "unknown"  # Type of asset captioned

# Main class
class VisionCaptioner:
    def __init__(self, api_key: str, *, images_per_request: int = IMAGES_PER_REQUEST):
        self.client = AsyncOpenAI(api_key=api_key)
        self.images_per_request = images_per_request
        logger.info("Initialized VisionCaptioner with model %s", MODEL)

    # public - Enhanced asset-aware interface
    async def caption_assets(self, assets: List[AssetInfo]) -> Dict[str, str]:
        """
        Caption a list of AssetInfo objects, returning a mapping of asset_id -> caption.
        
        This is the preferred method for the new Docling-based workflow.
        Process each asset individually to ensure completely separate descriptions.
        """
        if not assets:
            return {}

        logger.info("Processing %d assets for captioning (individual processing)", len(assets))
        
        # Process each asset individually to ensure separate descriptions
        sem = asyncio.Semaphore(3)  # Limit concurrency to avoid rate limits
        all_results = {}

        async def _worker(asset: AssetInfo):
            async with sem:
                return await self._call_openai_single_asset(asset)

        # Process all assets concurrently but individually
        caption_results = await asyncio.gather(*[_worker(asset) for asset in assets])
        
        # Collect results
        for asset, caption in zip(assets, caption_results):
            all_results[asset.asset_id] = caption

        logger.info("Successfully captioned %d assets individually", len(all_results))
        return all_results

    # public - Legacy interface for backward compatibility
    async def caption_images(self, images: List[bytes]) -> List[str]:
        """Return one caption per `images` item, in the same order."""
        if not images:
            return []

        logger.info("Processing %d images (legacy interface)", len(images))

        batches = [
            images[i : i + self.images_per_request]
            for i in range(0, len(images), self.images_per_request)
        ]

        # Fire the batches concurrently but not *too* fast.
        sem = asyncio.Semaphore(3)
        results: list[CaptionResult] = []

        async def _worker(batch: List[bytes], offset: int):
            async with sem:
                captions = await self._call_openai_legacy(batch)
                for idx, caption in enumerate(captions):
                    results.append(CaptionResult(
                        asset_id=str(offset + idx), 
                        caption=caption,
                        asset_type="image"
                    ))

        await asyncio.gather(
            *(_worker(batch, i * self.images_per_request) for i, batch in enumerate(batches))
        )

        # Re-order because batches resolve out-of-order
        sorted_results = sorted(results, key=lambda x: int(x.asset_id))
        return [r.caption for r in sorted_results]

    # internals
    @retry(
        reraise=True,
        wait=wait_random_exponential(multiplier=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def _call_openai_single_asset(self, asset: AssetInfo) -> str:
        """Process a single asset to ensure individual, standalone captions."""
        data_url = self._bytes_to_data_url(asset.image_bytes)
        
        # Select appropriate system prompt based on asset type
        system_prompt = SYSTEM_PROMPTS.get(asset.asset_type, SYSTEM_PROMPTS["default"])
        
        try:
            resp = await self.client.chat.completions.create(
                model=MODEL,
                temperature=0.2,
                max_tokens=200,  # Increased for more detailed descriptions
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": "Analyze this image and provide a detailed but concise description that captures all essential information for academic understanding:"},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]},
                ],
            )
            caption = resp.choices[0].message.content.strip()
            
            # Clean up any unwanted prefixes or formatting
            caption = caption.replace("This image shows", "").replace("The image shows", "").strip()
            if caption.startswith("shows"):
                caption = caption[5:].strip()
            
            return caption if caption else f"A {asset.asset_type} from page {asset.page_number}"
            
        except Exception as e:
            logger.error("Error calling OpenAI for asset %s: %s", asset.asset_id, e)
            return f"A {asset.asset_type} from page {asset.page_number}"

    @retry(
        reraise=True,
        wait=wait_random_exponential(multiplier=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def _call_openai_for_assets(self, assets: List[AssetInfo], asset_type: str) -> Dict[str, str]:
        """Process a batch of assets with type-appropriate prompting."""
        if not assets:
            return {}
            
        content_blocks = []
        for i, asset in enumerate(assets):
            data_url = self._bytes_to_data_url(asset.image_bytes)
            content_blocks.append({"type": "image_url", "image_url": {"url": data_url}})

        # Select appropriate system prompt based on asset type
        system_prompt = SYSTEM_PROMPTS.get(asset_type, SYSTEM_PROMPTS["default"])
        
        # Create explicit user message for individual captions
        user_text = (
            f"Analyze these {len(assets)} images and provide exactly {len(assets)} detailed descriptions, one per line. "
            f"Each line should be a comprehensive but concise analysis that captures essential information for academic understanding. "
            f"Include specific data points, relationships, and context when visible. "
            f"Do not reference other images (avoid 'The first image... The second image...'). "
            f"Provide {len(assets)} detailed individual descriptions:"
        )
        
        try:
            resp = await self.client.chat.completions.create(
                model=MODEL,
                temperature=0.2,
                max_tokens=200 * len(assets),   # Increased for detailed descriptions
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [{"type": "text", "text": user_text}] + content_blocks},
                ],
            )
            text = resp.choices[0].message.content
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            
            # Map captions back to asset IDs
            result = {}
            for i, asset in enumerate(assets):
                if i < len(lines):
                    result[asset.asset_id] = lines[i]
                else:
                    # Fallback if we don't get enough captions
                    result[asset.asset_id] = f"A {asset_type} from page {asset.page_number}"
                    logger.warning("Insufficient captions for asset %s", asset.asset_id)
            
            return result
            
        except Exception as e:
            logger.error("Error calling OpenAI for %s assets: %s", asset_type, e)
            # Return fallback captions
            return {
                asset.asset_id: f"A {asset_type} from page {asset.page_number}"
                for asset in assets
            }

    @retry(
        reraise=True,
        wait=wait_random_exponential(multiplier=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def _call_openai_legacy(self, imgs: List[bytes]) -> List[str]:
        """Legacy OpenAI request for backward compatibility."""
        content_blocks = []
        for img in imgs:
            data_url = self._bytes_to_data_url(img)
            content_blocks.append({"type": "image_url", "image_url": {"url": data_url}})

        resp = await self.client.chat.completions.create(
            model=MODEL,
            temperature=0.2,
            max_tokens=200 * len(imgs),   # Increased for detailed descriptions
            messages=[
                {"role": "system", "content": SYSTEM_PROMPTS["default"]},
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


