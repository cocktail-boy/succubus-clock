"""
Async batch idle-animation Image-to-Video runner for:
  bytedance/seedance-2.0/fast/image-to-video

For the anchor image and each stem in ./successful_variations.txt, generate one
loop-friendly idle animation by using the same PNG as both the start and end frame.
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fal_client
import requests

# ---- Config ----
MODEL = "bytedance/seedance-2.0/fast/image-to-video"

ANCHOR_IMAGE = Path("succubus_anchor_01_4x4") / "anchor.png"
VARIATIONS_DIR = Path("variations")
SUCCESSFUL_VARIATIONS_FILE = Path(__file__).resolve().parent / "successful_variations.txt"
OUTPUT_DIR = Path("video_outputs_seedance_2_0") / "idle_animations"

PROMPT = (
    "Create a subtle looping video game idle animation from the provided image. "
    "Use gentle breathing motion, tiny posture shifts, slight hair and cloth movement, "
    "and a steady locked camera. Preserve the character, composition, colors, and painterly style. "
    "The first and last frames should match closely for a seamless idle loop. "
    "Avoid walking, posing changes, scene changes, jitter, warping, flicker, extra limbs, "
    "distorted hands, or facial deformation."
)

# Fast tier API: "480p" | "720p" only.
RESOLUTION = "720p"

# Per API: "auto" or string seconds from 4 to 15.
IDLE_DURATION = "4"

# Per API: "auto" | aspect presets.
ASPECT_RATIO = "auto"

GENERATE_AUDIO = False

# Omit from the request when None (random / server default). Optional per schema.
SEED: Optional[int] = None

# Required by some agreements: stable ID per end customer. Also read from env FAL_END_USER_ID if unset here.
END_USER_ID: Optional[str] = "cocktailboy"

CONCURRENCY = 12

# Include the anchor idle clip before successful variation clips.
INCLUDE_ANCHOR = True

# After sorting by input path, skip this many image jobs (0 = from first).
SKIP_FIRST = 0

# After SKIP_FIRST, only this many image jobs are processed. None = all remaining images.
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
    if IDLE_DURATION not in _ALLOWED_DUR:
        raise ValueError(f"IDLE_DURATION must be one of {sorted(_ALLOWED_DUR)}; got {IDLE_DURATION!r}")
    if not PROMPT or not PROMPT.strip():
        raise ValueError("PROMPT must be a non-empty string")
    if NUM_FILES_TO_PROCESS is not None and NUM_FILES_TO_PROCESS < 1:
        raise ValueError(f"NUM_FILES_TO_PROCESS must be >= 1 or None; got {NUM_FILES_TO_PROCESS!r}")
    if SKIP_FIRST < 0:
        raise ValueError(f"SKIP_FIRST must be >= 0; got {SKIP_FIRST!r}")
    if INCLUDE_ANCHOR and not ANCHOR_IMAGE.exists():
        raise FileNotFoundError(f"Anchor image not found: {ANCHOR_IMAGE.resolve()}")
    if not VARIATIONS_DIR.exists():
        raise FileNotFoundError(f"Variations directory not found: {VARIATIONS_DIR.resolve()}")
    if not SUCCESSFUL_VARIATIONS_FILE.exists():
        raise FileNotFoundError(f"Successful variations list not found: {SUCCESSFUL_VARIATIONS_FILE.resolve()}")


def _resolved_end_user_id() -> Optional[str]:
    return (END_USER_ID or os.environ.get("FAL_END_USER_ID") or "").strip() or None


def _successful_variation_stems() -> List[str]:
    stems: List[str] = []
    for line in SUCCESSFUL_VARIATIONS_FILE.read_text(encoding="utf-8").splitlines():
        stem = line.strip()
        if not stem or stem.startswith("#"):
            continue
        stems.append(Path(stem).stem)
    return stems


def _image_jobs() -> List[Tuple[str, Path]]:
    jobs: List[Tuple[str, Path]] = []
    if INCLUDE_ANCHOR:
        jobs.append(("anchor", ANCHOR_IMAGE))

    for stem in _successful_variation_stems():
        variation_path = VARIATIONS_DIR / f"{stem}.png"
        if variation_path.exists():
            jobs.append((stem, variation_path))
        else:
            print(f"[{stem}] WARN missing variation image: {variation_path}")

    jobs = sorted(jobs, key=lambda item: str(item[1]))
    return jobs


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


async def generate_idle_video(
    *,
    label: str,
    image_url: str,
    out_path: Path,
) -> None:
    print(f"[{label}] submitting {IDLE_DURATION}s idle animation...")

    input_payload: Dict[str, Any] = {
        "prompt": PROMPT,
        "image_url": image_url,
        "end_image_url": image_url,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "duration": IDLE_DURATION,
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


async def process_image(name: str, image_path: Path, *, sem: asyncio.Semaphore) -> None:
    async with sem:
        out_path = OUTPUT_DIR / f"{name}_idle_{IDLE_DURATION}s.mp4"
        if out_path.exists():
            print(f"[{name}] already done, skipping.")
            return

        print(f"[{name}] uploading source image...")
        image_url = await fal_client.upload_file_async(str(image_path))
        await generate_idle_video(label=name, image_url=image_url, out_path=out_path)


async def main() -> None:
    _validate_config()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_jobs = _image_jobs()
    if not all_jobs:
        print("No idle animation image jobs found.")
        return
    if SKIP_FIRST >= len(all_jobs):
        print(f"SKIP_FIRST={SKIP_FIRST} but only {len(all_jobs)} image job(s) - nothing left to process.")
        return

    jobs = all_jobs[SKIP_FIRST:]
    if NUM_FILES_TO_PROCESS is not None:
        jobs = jobs[:NUM_FILES_TO_PROCESS]

    if not jobs:
        print("No idle animation jobs to process after SKIP_FIRST / limit.")
        return

    print(f"Processing {len(jobs)} idle animation image job(s).")
    for name, image_path in jobs:
        print(f"   -> {name}: {image_path}")

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [process_image(name, image_path, sem=sem) for name, image_path in jobs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    failures = 0
    for (name, _image_path), result in zip(jobs, results):
        if isinstance(result, Exception):
            failures += 1
            print(f"[{name}] WARN {type(result).__name__}: {result}")

    if failures:
        print(f"Done with {failures}/{len(jobs)} idle animation failure(s).")
    else:
        print(f"Done. Saved {len(jobs)} idle animation video(s) to {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
