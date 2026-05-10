"""
Async batch image generator for clock digits.

Uses fal.ai's nano-banana-2/edit endpoint with the succubus anchor image as a
style reference to produce themed glyphs for each digit 0-9 plus a colon, then
runs each result through birefnet/v2 matting to extract a real alpha channel.
Outputs are saved as transparent-background PNGs in ./clock_digits.
"""

import asyncio
import base64
from pathlib import Path
from typing import Any, Dict, Optional

import fal_client
import requests

MODEL = "fal-ai/nano-banana-2/edit"
MATTING_MODEL = "fal-ai/birefnet/v2"
MATTING_VARIANT = "Matting"
MATTING_RESOLUTION = "2048x2048"

ANCHOR_IMAGE = Path("succubus_anchor_01_4x4") / "anchor.png"
OUTPUT_DIR = Path("clock_digits")

ASPECT_RATIO = "1:1"
RESOLUTION = "1K"
OUTPUT_FORMAT = "png"
NUM_IMAGES = 1
CONCURRENCY = 6

STYLE_DESCRIPTION = (
    "carved-bone glyph with deep crimson glow seeping from cracks, "
    "obsidian-black ornamental serifs, faint smoke and ember motes, "
    "subtle painterly texture matching the reference succubus artwork, "
    "ornamental but unambiguously legible"
)

PROMPT_TEMPLATE = (
    "Render the single character \"{glyph}\" as a tall, centered, fully "
    "isolated glyph on a fully transparent background. Style: " + STYLE_DESCRIPTION + ". "
    "The glyph must fill most of the frame with comfortable padding, be "
    "perfectly centered, occupy a single uniform width comparable to the "
    "other digits 0-9, and contain no other characters, frames, drop shadows "
    "outside the glyph, decorative borders, captions, watermarks, or background scenery. "
    "Match the color palette and painterly mood of the reference image, but produce "
    "a clean glyph asset with crisp silhouette suitable for compositing over video."
)

GLYPHS = [
    ("0", "0"),
    ("1", "1"),
    ("2", "2"),
    ("3", "3"),
    ("4", "4"),
    ("5", "5"),
    ("6", "6"),
    ("7", "7"),
    ("8", "8"),
    ("9", "9"),
    ("colon", ":"),
]


def _decode_data_uri(uri: str) -> Optional[bytes]:
    if not uri.startswith("data:"):
        return None
    _, _, payload = uri.partition(",")
    try:
        return base64.b64decode(payload)
    except Exception:
        return None


def get_image_url(result: Dict[str, Any]) -> Optional[str]:
    def find(obj: Any) -> Optional[str]:
        if not isinstance(obj, dict):
            return None
        images = obj.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict) and isinstance(first.get("url"), str):
                return first["url"]
        image = obj.get("image")
        if isinstance(image, dict) and isinstance(image.get("url"), str):
            return image["url"]
        return None

    return find(result) or find(result.get("data") if isinstance(result, dict) else None)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = _decode_data_uri(url)
    if payload is not None:
        dest.write_bytes(payload)
        return

    with requests.get(url, stream=True, timeout=180) as response:
        response.raise_for_status()
        with open(dest, "wb") as file:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    file.write(chunk)


async def generate_glyph(
    name: str,
    glyph: str,
    *,
    anchor_url: str,
    sem: asyncio.Semaphore,
) -> None:
    async with sem:
        out_path = OUTPUT_DIR / f"{name}.png"
        if out_path.exists():
            print(f"[{name}] already exists, skipping.")
            return

        prompt = PROMPT_TEMPLATE.format(glyph=glyph)
        print(f"[{name}] submitting...")

        input_payload: Dict[str, Any] = {
            "prompt": prompt,
            "image_urls": [anchor_url],
            "aspect_ratio": ASPECT_RATIO,
            "resolution": RESOLUTION,
            "num_images": NUM_IMAGES,
            "output_format": OUTPUT_FORMAT,
        }

        handler = await fal_client.submit_async(MODEL, arguments=input_payload)

        async for event in handler.iter_events(with_logs=False):
            status = getattr(event, "status", None)
            if status:
                print(f"[{name}] {status}")

        result: Dict[str, Any] = await handler.get()
        image_url = get_image_url(result)
        if not image_url:
            raise ValueError(f"[{name}] No image URL in result: {result}")

        print(f"[{name}] matting...")
        matting_handler = await fal_client.submit_async(
            MATTING_MODEL,
            arguments={
                "image_url": image_url,
                "model": MATTING_VARIANT,
                "operating_resolution": MATTING_RESOLUTION,
                "output_format": "png",
                "refine_foreground": True,
            },
        )
        matting_result: Dict[str, Any] = await matting_handler.get()
        matted_url = get_image_url(matting_result)
        if not matted_url:
            raise ValueError(f"[{name}] No matted image URL in result: {matting_result}")

        await asyncio.to_thread(download, matted_url, out_path)
        print(f"[{name}] OK saved -> {out_path}")


async def main() -> None:
    if not ANCHOR_IMAGE.exists():
        raise FileNotFoundError(f"Anchor image not found: {ANCHOR_IMAGE.resolve()}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Uploading anchor reference: {ANCHOR_IMAGE}")
    anchor_url = await fal_client.upload_file_async(str(ANCHOR_IMAGE))

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [generate_glyph(name, glyph, anchor_url=anchor_url, sem=sem) for name, glyph in GLYPHS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    failures = 0
    for (name, _), result in zip(GLYPHS, results):
        if isinstance(result, Exception):
            failures += 1
            print(f"[{name}] WARN {type(result).__name__}: {result}")

    if failures:
        print(f"Done with {failures}/{len(GLYPHS)} glyph failure(s).")
    else:
        print(f"Done. Saved {len(GLYPHS)} glyphs to {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
