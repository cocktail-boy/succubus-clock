"""
Async batch Image-to-Video runner for:
  bytedance/seedance-2.0/fast/image-to-video

For every PNG in ./variations, generate two videos:
  1. succubus_anchor_01_4x4/anchor.png -> variations/<name>.png (8 sec)
  2. variations/<name>.png -> succubus_anchor_01_4x4/anchor.png (4 sec)
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Optional

import fal_client
import requests

# ---- Config ----
MODEL = "bytedance/seedance-2.0/fast/image-to-video"

ANCHOR_IMAGE = Path("succubus_anchor_01_4x4") / "anchor.png"
VARIATIONS_DIR = Path("variations")
OUTPUT_DIR = Path("video_outputs_seedance_2_0") / "anchor_variations"

PROMPT = (
    "Preserve the character, composition, colors, and painterly style. "
    "Create a smooth cinematic transition between the provided start and end frames, "
    "with gentle natural body motion, subtle cloth movement, and a steady camera. "
    "Avoid jitter, warping, flicker, extra limbs, distorted hands, or sudden scene changes."
)

# Fast tier API: "480p" | "720p" only.
RESOLUTION = "720p"

# Forward clip requested by the user.
FORWARD_DURATION = "8"

# Return clip requested by the user.
RETURN_DURATION = "4"

# Per API: "auto" | aspect presets.
ASPECT_RATIO = "auto"

GENERATE_AUDIO = False

# Omit from the request when None (random / server default). Optional per schema.
SEED: Optional[int] = None

# Required by some agreements: stable ID per end customer. Also read from env FAL_END_USER_ID if unset here.
END_USER_ID: Optional[str] = "cocktailboy"

CONCURRENCY = 20

# After sorting by path, skip this many variation files (0 = from first).
SKIP_FIRST = 0

# After SKIP_FIRST, only this many files are processed. None = all remaining files in VARIATIONS_DIR.
NUM_FILES_TO_PROCESS: Optional[int] = None

# ---- Validation ----
_ALLOWED_ASPECTS = {"auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}
_ALLOWED_RES = {"480p", "720p"}
_ALLOWED_DUR = {"auto", *(str(n) for n in range(4, 16))}


def _validate_config() -> None:
    if ASPECT_RATIO not in _ALLOWED_ASPECTS:
        raise ValueError(f"ASPECT_RATIO must be one of {sorted(_ALLOWED_ASPECTS)}; got {ASPECT_RATIO!r}")
    if RESOLUTION not in _ALLOWED_RES:
        raise ValueError(f"RESOLUTION must be one of {sorted(_ALLOWED_RES)}; got {RESOLUTION!r}")
    for label, duration in (("FORWARD_DURATION", FORWARD_DURATION), ("RETURN_DURATION", RETURN_DURATION)):
        if duration not in _ALLOWED_DUR:
            raise ValueError(f"{label} must be one of {sorted(_ALLOWED_DUR)}; got {duration!r}")
    if not PROMPT or not PROMPT.strip():
        raise ValueError("PROMPT must be a non-empty string")
    if NUM_FILES_TO_PROCESS is not None and NUM_FILES_TO_PROCESS < 1:
        raise ValueError(f"NUM_FILES_TO_PROCESS must be >= 1 or None; got {NUM_FILES_TO_PROCESS!r}")
    if SKIP_FIRST < 0:
        raise ValueError(f"SKIP_FIRST must be >= 0; got {SKIP_FIRST!r}")
    if not ANCHOR_IMAGE.exists():
        raise FileNotFoundError(f"Anchor image not found: {ANCHOR_IMAGE.resolve()}")
    if not VARIATIONS_DIR.exists():
        raise FileNotFoundError(f"Variations directory not found: {VARIATIONS_DIR.resolve()}")


def _resolved_end_user_id() -> Optional[str]:
    return (END_USER_ID or os.environ.get("FAL_END_USER_ID") or "").strip() or None


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=180) as response:
        response.raise_for_status()
        with open(dest, "wb") as file:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    file.write(chunk)


def get_video_url(result: Dict[str, Any]) -> Optional[str]:
    if isinstance(result.get("video"), dict) and result["video"].get("url"):
        return result["video"]["url"]

    data = result.get("data")
    if isinstance(data, dict) and isinstance(data.get("video"), dict) and data["video"].get("url"):
        return data["video"]["url"]

    if isinstance(result.get("video_url"), str):
        return result["video_url"]
    if isinstance(data, dict) and isinstance(data.get("video_url"), str):
        return data["video_url"]

    return None


async def generate_video(
    *,
    label: str,
    start_image_url: str,
    end_image_url: str,
    duration: str,
    out_path: Path,
) -> None:
    print(f"[{label}] submitting {duration}s video...")

    input_payload: Dict[str, Any] = {
        "prompt": PROMPT,
        "image_url": start_image_url,
        "end_image_url": end_image_url,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "duration": duration,
        "generate_audio": GENERATE_AUDIO,
    }
    if SEED is not None:
        input_payload["seed"] = SEED
    end_user_id = _resolved_end_user_id()
    if end_user_id:
        input_payload["end_user_id"] = end_user_id

    handler = await fal_client.submit_async(MODEL, arguments=input_payload)

    async for event in handler.iter_events(with_logs=False):
        status = getattr(event, "status", None)
        if status:
            print(f"[{label}] {status}")

    result: Dict[str, Any] = await handler.get()
    video_url = get_video_url(result)
    if not video_url:
        raise ValueError(f"[{label}] No video URL in result: {result}")

    await asyncio.to_thread(download, video_url, out_path)
    print(f"[{label}] OK saved -> {out_path}")


async def process_variation(
    variation_path: Path,
    *,
    anchor_url: str,
    sem: asyncio.Semaphore,
) -> None:
    async with sem:
        forward_out = OUTPUT_DIR / f"{variation_path.stem}_anchor_to_variation_{FORWARD_DURATION}s.mp4"
        return_out = OUTPUT_DIR / f"{variation_path.stem}_variation_to_anchor_{RETURN_DURATION}s.mp4"
        if forward_out.exists() and return_out.exists():
            print(f"[{variation_path.name}] already done, skipping.")
            return

        print(f"[{variation_path.name}] uploading variation...")
        variation_url = await fal_client.upload_file_async(str(variation_path))

        await generate_video(
            label=f"{variation_path.stem} anchor->variation",
            start_image_url=anchor_url,
            end_image_url=variation_url,
            duration=FORWARD_DURATION,
            out_path=forward_out,
        )
        await generate_video(
            label=f"{variation_path.stem} variation->anchor",
            start_image_url=variation_url,
            end_image_url=anchor_url,
            duration=RETURN_DURATION,
            out_path=return_out,
        )


async def main() -> None:
    _validate_config()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_variations = sorted(VARIATIONS_DIR.glob("*.png"))
    if not all_variations:
        print(f"No PNG variations found in {VARIATIONS_DIR.resolve()}")
        return
    if SKIP_FIRST >= len(all_variations):
        print(
            f"SKIP_FIRST={SKIP_FIRST} but only {len(all_variations)} variation image(s) in "
            f"{VARIATIONS_DIR.resolve()} - nothing left to process."
        )
        return

    variations = all_variations[SKIP_FIRST:]
    if NUM_FILES_TO_PROCESS is not None:
        variations = variations[:NUM_FILES_TO_PROCESS]

    if not variations:
        print(f"No variations to process after SKIP_FIRST / limit in {VARIATIONS_DIR.resolve()}")
        return

    print(f"Uploading anchor image: {ANCHOR_IMAGE}")
    anchor_url = await fal_client.upload_file_async(str(ANCHOR_IMAGE))

    print(f"Processing {len(variations)} variation image(s).")
    for variation in variations:
        print(f"   -> {variation.name}")

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [process_variation(variation, anchor_url=anchor_url, sem=sem) for variation in variations]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    failures = 0
    for variation, result in zip(variations, results):
        if isinstance(result, Exception):
            failures += 1
            print(f"[{variation.name}] WARN {type(result).__name__}: {result}")

    expected_videos = len(variations) * 2
    if failures:
        print(f"Done with {failures}/{len(variations)} variation failure(s).")
    else:
        print(f"Done. Saved {expected_videos} videos to {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
