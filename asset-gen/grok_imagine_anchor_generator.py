"""
Async anchor-only batch Text-to-Image generator for xai/grok-imagine-image/quality.

Generates candidate anchor images for a single character identity.
Uses CHARACTER SHEET + Variation N from succubus_20_variations.txt.

Docs: https://fal.ai/models/xai/grok-imagine-image/quality/text-to-image/api
"""

import asyncio
import re
from pathlib import Path
from typing import Any, Dict

import fal_lib

fal_lib.setup_utf8_console()

# ---- Config ----
MODEL = "xai/grok-imagine-image/quality/text-to-image"
SOURCE_PROMPTS_FILE = Path(__file__).resolve().parent / "succubus_20_variations.txt"

OUTPUT_BASE_DIR = Path("./image_outputs_grok_imagine_quality_fal")
OUTPUT_SUBDIR = "succubus_anchor_portrait_9_16"

ANCHOR_VARIATION_NUMBER = 1
BATCH_COUNT = 1
IMAGES_PER_BATCH = 4
API_MAX_NUM_IMAGES = 4
CONCURRENCY = 10

ASPECT_RATIO = "9:16"      # see _ALLOWED_ASPECTS below
RESOLUTION = "2k"          # "1k", "2k"
OUTPUT_FORMAT = "png"      # "jpeg", "png", "webp"

_ALLOWED_ASPECTS = {
    "2:1", "20:9", "19.5:9", "16:9", "4:3", "3:2",
    "1:1",
    "2:3", "3:4", "9:16", "9:19.5", "9:20", "1:2",
}
_ALLOWED_RESOLUTION = {"1k", "2k"}
_ALLOWED_FORMAT = {"jpeg", "png", "webp"}
_HEADING_MARKER = "=" * 64


def _validate_config() -> None:
    if ASPECT_RATIO not in _ALLOWED_ASPECTS:
        raise ValueError(
            f"ASPECT_RATIO must be one of {sorted(_ALLOWED_ASPECTS)}; got {ASPECT_RATIO!r}"
        )
    if RESOLUTION not in _ALLOWED_RESOLUTION:
        raise ValueError(f"RESOLUTION must be one of {sorted(_ALLOWED_RESOLUTION)}; got {RESOLUTION!r}")
    if OUTPUT_FORMAT not in _ALLOWED_FORMAT:
        raise ValueError(f"OUTPUT_FORMAT must be one of {sorted(_ALLOWED_FORMAT)}; got {OUTPUT_FORMAT!r}")
    if BATCH_COUNT < 1:
        raise ValueError("BATCH_COUNT must be >= 1")
    if IMAGES_PER_BATCH < 1:
        raise ValueError("IMAGES_PER_BATCH must be >= 1")
    if API_MAX_NUM_IMAGES < 1:
        raise ValueError("API_MAX_NUM_IMAGES must be >= 1")


# ---- Prompt-file parsing (script-specific format) ----
def _extract_between_markers(text: str, header: str) -> str:
    marker_block = f"{_HEADING_MARKER}\n{header}\n{_HEADING_MARKER}\n"
    start = text.find(marker_block)
    if start == -1:
        raise ValueError(f"Could not find section header: {header!r}")
    start += len(marker_block)
    next_idx = text.find(_HEADING_MARKER, start)
    section = (text[start:] if next_idx == -1 else text[start:next_idx]).strip()
    if not section:
        raise ValueError(f"Section is empty: {header!r}")
    return section


def _extract_variation_prompt(variation_block: str, variation_number: int) -> str:
    pattern = re.compile(
        rf"^---\s*{variation_number:02d}\.\s*.+?---\s*$([\s\S]*?)(?=^---\s*\d{{2}}\.\s*.+?---\s*$|\Z)",
        re.MULTILINE,
    )
    m = pattern.search(variation_block)
    if not m:
        raise ValueError(f"Could not find variation #{variation_number:02d}")
    body = m.group(1).strip()
    if not body:
        raise ValueError(f"Variation #{variation_number:02d} prompt body is empty")
    return body


def load_anchor_prompt(path: Path, variation_number: int) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"SOURCE_PROMPTS_FILE not found: {path.resolve()}")

    text = path.read_text(encoding="utf-8")
    character_sheet = _extract_between_markers(text, "CHARACTER SHEET (paste verbatim into every prompt)")
    variation_block = _extract_between_markers(text, "VARIATION PROMPTS")
    variation_prompt = _extract_variation_prompt(variation_block, variation_number)

    if "[CHARACTER SHEET]" in variation_prompt:
        return variation_prompt.replace("[CHARACTER SHEET]", character_sheet).strip()
    return f"{character_sheet}\n\n{variation_prompt}".strip()


def make_payload(prompt: str, num_images: int) -> Dict[str, Any]:
    return {
        "prompt": prompt,
        "num_images": num_images,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "output_format": OUTPUT_FORMAT,
    }


async def run_one_request(
    *,
    prompt: str,
    batch_dir: Path,
    batch_idx: int,
    req_idx: int,
    req_image_count: int,
    start_global_idx: int,
) -> int:
    tag = f"batch{batch_idx:02d}-req{req_idx:02d}"
    print(f"[{tag}] submitting request for {req_image_count} image(s)...", flush=True)

    result = await fal_lib.submit_and_get(MODEL, make_payload(prompt, req_image_count), log_tag=tag)
    images = fal_lib.extract_images(result)
    if not images:
        raise ValueError("No image URLs in response result")

    saved_n = 0
    for i, image in enumerate(images):
        out_path = batch_dir / f"anchor_b{batch_idx:02d}_{start_global_idx + i:02d}.{OUTPUT_FORMAT}"
        await fal_lib.download_async(image["url"], out_path)
        saved_n += 1
        print(f"[{tag}] saved -> {out_path}", flush=True)
    return saved_n


async def generate_batch(batch_idx: int, prompt: str, output_root: Path, sem: asyncio.Semaphore) -> int:
    batch_dir = output_root / f"batch_{batch_idx:02d}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    async with sem:
        target = IMAGES_PER_BATCH
        req_total = (target + API_MAX_NUM_IMAGES - 1) // API_MAX_NUM_IMAGES
        saved_total = 0

        for req_idx in range(1, req_total + 1):
            req_n = min(API_MAX_NUM_IMAGES, target - saved_total)
            if req_n <= 0:
                break
            try:
                saved_n = await run_one_request(
                    prompt=prompt,
                    batch_dir=batch_dir,
                    batch_idx=batch_idx,
                    req_idx=req_idx,
                    req_image_count=req_n,
                    start_global_idx=saved_total + 1,
                )
                saved_total += saved_n
            except Exception as exc:
                print(
                    f"[batch{batch_idx:02d}] request {req_idx} failed: {fal_lib.short_exc(exc)}",
                    flush=True,
                )

        print(f"[batch{batch_idx:02d}] done: saved {saved_total}/{target}", flush=True)
        return saved_total


async def main() -> None:
    _validate_config()
    prompt = load_anchor_prompt(SOURCE_PROMPTS_FILE, ANCHOR_VARIATION_NUMBER)

    output_root = OUTPUT_BASE_DIR / OUTPUT_SUBDIR
    output_root.mkdir(parents=True, exist_ok=True)

    total_target = BATCH_COUNT * IMAGES_PER_BATCH
    print(
        f"Grok Imagine (quality) anchor generator: {BATCH_COUNT} batches x {IMAGES_PER_BATCH} images "
        f"({total_target} total)",
        flush=True,
    )
    print(f"Source: {SOURCE_PROMPTS_FILE.resolve()} | Variation: {ANCHOR_VARIATION_NUMBER:02d}", flush=True)
    print(f"Output: {output_root.resolve()}", flush=True)
    print(f"Aspect: {ASPECT_RATIO} | Resolution: {RESOLUTION} | Format: {OUTPUT_FORMAT}", flush=True)
    print(f"Concurrency: {CONCURRENCY} | API max num_images/request: {API_MAX_NUM_IMAGES}", flush=True)
    print(flush=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [generate_batch(i, prompt, output_root, sem) for i in range(1, BATCH_COUNT + 1)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    saved_total = 0
    crashed = 0
    for r in results:
        if isinstance(r, Exception):
            crashed += 1
        else:
            saved_total += r

    print(flush=True)
    print(f"Saved {saved_total}/{total_target} total image(s) to {output_root.resolve()}", flush=True)
    if crashed:
        print(f"Batches crashed unexpectedly: {crashed}/{BATCH_COUNT}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
