"""
Async batch image-edit generator for openai/gpt-image-2/edit.

- Uses the project anchor image as the reference input (image_urls[0]).
- Loads succubus x Die-with-Zero prompts from
  succubus_diewithzero_variations.txt.
- Generates Variation START..END with edit mode.
"""

import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import fal_client

import fal_lib

ImageSize = Union[str, Dict[str, int]]
VariationEntry = Tuple[int, str]

fal_lib.setup_utf8_console()

# ---- Config ----
MODEL = "openai/gpt-image-2/edit"
PROMPTS_FILE = Path(__file__).resolve().parent / "succubus_diewithzero_variations.txt"
ANCHOR_IMAGE_PATH = Path("succubus_anchor_01_4x4") / "anchor.png"

OUTPUT_ROOT = Path("./succubus_variations_diewithzero")

START_VARIATION = 1
END_VARIATION = 6
NUM_IMAGES_PER_VARIATION = 4
API_MAX_NUM_IMAGES = 4
CONCURRENCY = 20

IMAGE_SIZE: ImageSize = {"width": 720, "height": 1280}
QUALITY = "medium"  # "low", "medium", "high"
OUTPUT_FORMAT = "png"  # "jpeg", "png", "webp"

BYOK_OPENAI_API_KEY: Optional[str] = None

_ALLOWED_PRESET_SIZES = {
    "auto",
    "square_hd",
    "square",
    "portrait_4_3",
    "portrait_16_9",
    "landscape_4_3",
    "landscape_16_9",
}
_ALLOWED_QUALITY = {"low", "medium", "high"}
_ALLOWED_FORMAT = {"jpeg", "png", "webp"}
_HEADING_MARKER = "=" * 64


def _validate_config() -> None:
    if isinstance(IMAGE_SIZE, str):
        if IMAGE_SIZE not in _ALLOWED_PRESET_SIZES:
            raise ValueError(
                f"IMAGE_SIZE string must be one of {sorted(_ALLOWED_PRESET_SIZES)}; got {IMAGE_SIZE!r}"
            )
    elif isinstance(IMAGE_SIZE, dict):
        w, h = IMAGE_SIZE.get("width"), IMAGE_SIZE.get("height")
        if not isinstance(w, int) or not isinstance(h, int) or w <= 0 or h <= 0:
            raise ValueError('IMAGE_SIZE dict must be {"width": int, "height": int} with positive values')
    else:
        raise ValueError("IMAGE_SIZE must be a preset string or a width/height dict")
    if QUALITY not in _ALLOWED_QUALITY:
        raise ValueError(f"QUALITY must be one of {sorted(_ALLOWED_QUALITY)}; got {QUALITY!r}")
    if OUTPUT_FORMAT not in _ALLOWED_FORMAT:
        raise ValueError(f"OUTPUT_FORMAT must be one of {sorted(_ALLOWED_FORMAT)}; got {OUTPUT_FORMAT!r}")
    if NUM_IMAGES_PER_VARIATION < 1:
        raise ValueError("NUM_IMAGES_PER_VARIATION must be >= 1")
    if API_MAX_NUM_IMAGES < 1:
        raise ValueError("API_MAX_NUM_IMAGES must be >= 1")
    if START_VARIATION < 1 or END_VARIATION < START_VARIATION:
        raise ValueError("Variation range is invalid")
    if not ANCHOR_IMAGE_PATH.is_file():
        raise FileNotFoundError(f"Anchor image not found: {ANCHOR_IMAGE_PATH.resolve()}")


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


def load_variation_prompts(path: Path) -> List[VariationEntry]:
    if not path.is_file():
        raise FileNotFoundError(f"PROMPTS_FILE not found: {path.resolve()}")

    text = path.read_text(encoding="utf-8")
    character_sheet = _extract_between_markers(text, "CHARACTER SHEET (paste verbatim into every prompt)")
    variation_block = _extract_between_markers(text, "VARIATION PROMPTS")

    pattern = re.compile(
        r"^---\s*(\d{2})\.\s*(.+?)\s*---\s*$([\s\S]*?)(?=^---\s*\d{2}\.\s*.+?---\s*$|\Z)",
        re.MULTILINE,
    )
    out: List[VariationEntry] = []
    for m in pattern.finditer(variation_block):
        variation_num = int(m.group(1))
        body = m.group(3).strip()
        if not body:
            continue
        full_prompt = body.replace("[CHARACTER SHEET]", character_sheet).strip()
        out.append((variation_num, full_prompt))

    if not out:
        raise ValueError(f"No variations found in {path}")

    filtered = [item for item in out if START_VARIATION <= item[0] <= END_VARIATION]
    if not filtered:
        raise ValueError(
            f"No variations found in configured range [{START_VARIATION}, {END_VARIATION}] in {path}"
        )
    return filtered


def _non_clobber_path(path: Path) -> Path:
    """Return a unique path by appending _rN if target exists."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    i = 1
    while True:
        candidate = path.with_name(f"{stem}_r{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def make_payload(prompt: str, anchor_url: str, num_images: int) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "prompt": prompt,
        "image_urls": [anchor_url],
        "image_size": IMAGE_SIZE,
        "quality": QUALITY,
        "num_images": num_images,
        "output_format": OUTPUT_FORMAT,
    }
    if BYOK_OPENAI_API_KEY:
        payload["openai_api_key"] = BYOK_OPENAI_API_KEY
    return payload


async def generate_for_variation(
    *,
    variation_num: int,
    prompt: str,
    anchor_url: str,
    output_root: Path,
    sem: asyncio.Semaphore,
) -> int:
    vdir = output_root / f"variation_{variation_num:02d}"
    vdir.mkdir(parents=True, exist_ok=True)

    async with sem:
        target = NUM_IMAGES_PER_VARIATION
        req_count = (target + API_MAX_NUM_IMAGES - 1) // API_MAX_NUM_IMAGES
        saved = 0
        tag = f"v{variation_num:02d}"

        for req_i in range(1, req_count + 1):
            req_n = min(API_MAX_NUM_IMAGES, target - saved)
            if req_n <= 0:
                break

            rtag = f"{tag}-r{req_i}"
            print(f"[{rtag}] submitting {req_n} image(s)...", flush=True)
            try:
                result = await fal_lib.submit_and_get(
                    MODEL, make_payload(prompt, anchor_url, req_n), log_tag=rtag,
                )
                images = fal_lib.extract_images(result)
                if not images:
                    raise ValueError("No image URLs in response result")

                for i, image in enumerate(images):
                    base_path = vdir / f"succubus_dwz_v{variation_num:02d}_{saved + i + 1:02d}.{OUTPUT_FORMAT}"
                    out_path = _non_clobber_path(base_path)
                    await fal_lib.download_async(image["url"], out_path)
                    print(f"[{rtag}] saved -> {out_path}", flush=True)
                saved += len(images)
            except Exception as exc:
                print(f"[{rtag}] FAIL: {fal_lib.short_exc(exc)}", flush=True)

        print(f"[{tag}] done: {saved}/{target}", flush=True)
        return saved


async def main() -> None:
    _validate_config()
    variations = load_variation_prompts(PROMPTS_FILE)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    anchor_abs = ANCHOR_IMAGE_PATH.resolve()
    print(f"Uploading anchor image: {anchor_abs}", flush=True)
    anchor_url = await fal_client.upload_file_async(str(anchor_abs))
    print("Anchor uploaded.", flush=True)

    size_repr = IMAGE_SIZE if isinstance(IMAGE_SIZE, str) else f"{IMAGE_SIZE['width']}x{IMAGE_SIZE['height']}"
    total_target = len(variations) * NUM_IMAGES_PER_VARIATION
    print(
        f"GPT Image 2 edit run (Die with Zero): variations {START_VARIATION:02d}-{END_VARIATION:02d} "
        f"({len(variations)} prompts), {NUM_IMAGES_PER_VARIATION} image(s) each = {total_target} total",
        flush=True,
    )
    print(f"Prompt file: {PROMPTS_FILE.resolve()}", flush=True)
    print(f"Output: {OUTPUT_ROOT.resolve()}", flush=True)
    print(f"Size: {size_repr} | Quality: {QUALITY} | Format: {OUTPUT_FORMAT}", flush=True)
    print(f"Concurrency: {CONCURRENCY} | API max num_images/request: {API_MAX_NUM_IMAGES}", flush=True)
    print(flush=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        generate_for_variation(
            variation_num=vnum,
            prompt=prompt,
            anchor_url=anchor_url,
            output_root=OUTPUT_ROOT,
            sem=sem,
        )
        for vnum, prompt in variations
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    saved_total = 0
    crashed = 0
    for r in results:
        if isinstance(r, Exception):
            crashed += 1
        else:
            saved_total += r

    print(flush=True)
    print(f"Saved {saved_total}/{total_target} image(s) to {OUTPUT_ROOT.resolve()}", flush=True)
    if crashed:
        print(f"Variation tasks crashed unexpectedly: {crashed}/{len(variations)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
