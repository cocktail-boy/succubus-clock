"""
Async batch image generator for clock digits using OpenAI's gpt-image-1.5.

Calls images.edit with the succubus anchor image as a style reference and
relies on gpt-image-1.5's native `background="transparent"` support, so no
separate matting pass is required. Outputs are saved as transparent-background
PNGs in ./clock_digits.

Requires: OPENAI_API_KEY in the environment, and a recent `openai` SDK.
"""

import asyncio
import base64
import os
from pathlib import Path

from openai import AsyncOpenAI

MODEL = "gpt-image-1.5"

ANCHOR_IMAGE = Path("succubus_anchor_01_4x4") / "anchor.png"
OUTPUT_DIR = Path("clock_digits")

SIZE = "1024x1536"
QUALITY = "high"
BACKGROUND = "transparent"
OUTPUT_FORMAT = "png"
NUM_IMAGES = 1
CONCURRENCY = 4

STYLE_DESCRIPTION = (
    "carved-bone glyph with deep crimson glow seeping from cracks, "
    "obsidian-black ornamental serifs, faint ember motes, "
    "subtle painterly texture matching the reference succubus artwork, "
    "ornamental but unambiguously legible"
)

PROMPT_TEMPLATE = (
    "Render the single character \"{glyph}\" as a centered, fully isolated glyph "
    "on a fully transparent background. Style: " + STYLE_DESCRIPTION + ". "
    "Leave substantial transparent padding to the left and right and only modest padding "
    "above and below. Do not stretch the glyph horizontally to fill the canvas. "
    "All digits 0-9 should share a consistent height and stroke weight so they line up "
    "as a uniform set. The glyph must be perfectly centered and contain no other characters, "
    "frames, drop shadows outside the glyph, decorative borders, captions, watermarks, or "
    "background scenery. Match the color palette and painterly mood of the reference image, "
    "but produce a clean glyph asset with crisp silhouette suitable for compositing over video."
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


async def generate_glyph(
    client: AsyncOpenAI,
    name: str,
    glyph: str,
    *,
    anchor_bytes: bytes,
    sem: asyncio.Semaphore,
) -> None:
    async with sem:
        out_path = OUTPUT_DIR / f"{name}.png"
        if out_path.exists():
            print(f"[{name}] already exists, skipping.")
            return

        prompt = PROMPT_TEMPLATE.format(glyph=glyph)
        print(f"[{name}] submitting...")

        response = await client.images.edit(
            model=MODEL,
            image=("anchor.png", anchor_bytes, "image/png"),
            prompt=prompt,
            size=SIZE,
            quality=QUALITY,
            background=BACKGROUND,
            output_format=OUTPUT_FORMAT,
            n=NUM_IMAGES,
        )

        if not response.data:
            raise ValueError(f"[{name}] No image data in response")
        b64 = response.data[0].b64_json
        if not b64:
            raise ValueError(f"[{name}] No b64_json payload in response")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(out_path.write_bytes, base64.b64decode(b64))
        print(f"[{name}] OK saved -> {out_path}")


async def main() -> None:
    if not ANCHOR_IMAGE.exists():
        raise FileNotFoundError(f"Anchor image not found: {ANCHOR_IMAGE.resolve()}")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set in the environment.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading anchor reference: {ANCHOR_IMAGE}")
    anchor_bytes = ANCHOR_IMAGE.read_bytes()

    client = AsyncOpenAI()
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        generate_glyph(client, name, glyph, anchor_bytes=anchor_bytes, sem=sem)
        for name, glyph in GLYPHS
    ]
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
