"""
Async batch Image-to-Video runner for:
  bytedance/seedance-2.0/image-to-video

For every matching PNG pair in ./variations and ./variations_cute_concept,
generate two 4-second videos:
  1. variations/img_0001.png -> variations_cute_concept/img_0001_cute_concept_01.png
  2. variations_cute_concept/img_0001_cute_concept_01.png -> variations/img_0001.png

Pairs are matched by the shared file index, for example img_0001.
"""

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import fal_client
import requests

# ---- Config ----
MODEL = "bytedance/seedance-2.0/image-to-video"

REGULAR_VARIATIONS_DIR = Path("variations")
CUTE_VARIATIONS_DIR = Path("variations_cute_concept")
OUTPUT_DIR = Path("video_outputs_seedance_2_0") / "regular_cute_concept_transitions"

PROMPT = (
    "Preserve the same character identity, pose, composition, colors, and painterly style. "
    "Create a smooth cinematic transformation between the regular variation and the cute concept version, "
    "with gentle natural body motion, subtle cloth and hair movement, soft expression changes, and a steady camera. "
    "Keep the transition elegant and coherent. Avoid jitter, warping, flicker, extra limbs, distorted hands, "
    "facial deformation, or sudden scene changes."
)

# API supports "480p" | "720p" | "1080p". Keep 720p for cost savings.
RESOLUTION = "720p"

# Both directions are requested as 4-second clips.
DURATION = "4"

# Per API: "auto" | aspect presets.
ASPECT_RATIO = "auto"

GENERATE_AUDIO = False

# Omit from the request when None (random / server default). Optional per schema.
SEED: Optional[int] = None

# Required by some agreements: stable ID per end customer. Also read from env FAL_END_USER_ID if unset here.
END_USER_ID: Optional[str] = "cocktailboy"

CONCURRENCY = 20

# After sorting by index, skip this many paired files (0 = from first).
SKIP_FIRST = 0

# After SKIP_FIRST, only this many pairs are processed. None = all remaining pairs.
NUM_PAIRS_TO_PROCESS: Optional[int] = None

_INDEX_RE = re.compile(r"img_(\d+)", re.IGNORECASE)

# ---- Validation ----
_ALLOWED_ASPECTS = {"auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}
_ALLOWED_RES = {"480p", "720p", "1080p"}
_ALLOWED_DUR = {"auto", *(str(n) for n in range(4, 16))}


@dataclass(frozen=True)
class ImagePair:
    index: str
    regular_path: Path
    cute_path: Path


def _extract_index(path: Path) -> str:
    match = _INDEX_RE.search(path.stem)
    if not match:
        raise ValueError(f"Could not find an img_#### index in filename: {path.name}")
    return match.group(1).zfill(4)


def _paths_by_index(paths: Iterable[Path], *, label: str) -> Dict[str, Path]:
    indexed: Dict[str, Path] = {}
    for path in paths:
        index = _extract_index(path)
        if index in indexed:
            raise ValueError(
                f"Duplicate {label} image index img_{index}: {indexed[index].name} and {path.name}"
            )
        indexed[index] = path
    return indexed


def _build_pairs() -> list[ImagePair]:
    regular_by_index = _paths_by_index(sorted(REGULAR_VARIATIONS_DIR.glob("*.png")), label="regular")
    cute_by_index = _paths_by_index(sorted(CUTE_VARIATIONS_DIR.glob("*.png")), label="cute concept")

    if not regular_by_index:
        print(f"No PNG regular variations found in {REGULAR_VARIATIONS_DIR.resolve()}")
        return []
    if not cute_by_index:
        print(f"No PNG cute concept variations found in {CUTE_VARIATIONS_DIR.resolve()}")
        return []

    pairs: list[ImagePair] = []
    missing_cute: list[str] = []
    for index in sorted(regular_by_index):
        cute_path = cute_by_index.get(index)
        if cute_path is None:
            missing_cute.append(index)
            continue
        pairs.append(
            ImagePair(
                index=index,
                regular_path=regular_by_index[index],
                cute_path=cute_path,
            )
        )

    if missing_cute:
        joined = ", ".join(f"img_{index}" for index in missing_cute)
        print(f"WARN missing cute concept image(s) for: {joined}")

    extra_cute = sorted(set(cute_by_index) - set(regular_by_index))
    if extra_cute:
        joined = ", ".join(f"img_{index}" for index in extra_cute)
        print(f"WARN cute concept image(s) have no regular variation match: {joined}")

    return pairs


def _validate_config() -> None:
    if ASPECT_RATIO not in _ALLOWED_ASPECTS:
        raise ValueError(f"ASPECT_RATIO must be one of {sorted(_ALLOWED_ASPECTS)}; got {ASPECT_RATIO!r}")
    if RESOLUTION not in _ALLOWED_RES:
        raise ValueError(f"RESOLUTION must be one of {sorted(_ALLOWED_RES)}; got {RESOLUTION!r}")
    if DURATION not in _ALLOWED_DUR:
        raise ValueError(f"DURATION must be one of {sorted(_ALLOWED_DUR)}; got {DURATION!r}")
    if not PROMPT or not PROMPT.strip():
        raise ValueError("PROMPT must be a non-empty string")
    if NUM_PAIRS_TO_PROCESS is not None and NUM_PAIRS_TO_PROCESS < 1:
        raise ValueError(f"NUM_PAIRS_TO_PROCESS must be >= 1 or None; got {NUM_PAIRS_TO_PROCESS!r}")
    if SKIP_FIRST < 0:
        raise ValueError(f"SKIP_FIRST must be >= 0; got {SKIP_FIRST!r}")
    if not REGULAR_VARIATIONS_DIR.exists():
        raise FileNotFoundError(f"Regular variations directory not found: {REGULAR_VARIATIONS_DIR.resolve()}")
    if not CUTE_VARIATIONS_DIR.exists():
        raise FileNotFoundError(f"Cute concept variations directory not found: {CUTE_VARIATIONS_DIR.resolve()}")


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
    out_path: Path,
) -> None:
    print(f"[{label}] submitting {DURATION}s video...")

    input_payload: Dict[str, Any] = {
        "prompt": PROMPT,
        "image_url": start_image_url,
        "end_image_url": end_image_url,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "duration": DURATION,
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


async def process_pair(pair: ImagePair, *, sem: asyncio.Semaphore) -> None:
    async with sem:
        stem = f"img_{pair.index}"
        regular_to_cute_out = OUTPUT_DIR / f"{stem}_regular_to_cute_concept_{DURATION}s.mp4"
        cute_to_regular_out = OUTPUT_DIR / f"{stem}_cute_concept_to_regular_{DURATION}s.mp4"
        if regular_to_cute_out.exists() and cute_to_regular_out.exists():
            print(f"[{stem}] already done, skipping.")
            return

        print(f"[{stem}] uploading images...")
        regular_url, cute_url = await asyncio.gather(
            fal_client.upload_file_async(str(pair.regular_path)),
            fal_client.upload_file_async(str(pair.cute_path)),
        )

        if not regular_to_cute_out.exists():
            await generate_video(
                label=f"{stem} regular->cute concept",
                start_image_url=regular_url,
                end_image_url=cute_url,
                out_path=regular_to_cute_out,
            )
        else:
            print(f"[{stem} regular->cute concept] already exists, skipping.")

        if not cute_to_regular_out.exists():
            await generate_video(
                label=f"{stem} cute concept->regular",
                start_image_url=cute_url,
                end_image_url=regular_url,
                out_path=cute_to_regular_out,
            )
        else:
            print(f"[{stem} cute concept->regular] already exists, skipping.")


async def main() -> None:
    _validate_config()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_pairs = _build_pairs()
    if not all_pairs:
        return
    if SKIP_FIRST >= len(all_pairs):
        print(
            f"SKIP_FIRST={SKIP_FIRST} but only {len(all_pairs)} matched image pair(s) - "
            "nothing left to process."
        )
        return

    pairs = all_pairs[SKIP_FIRST:]
    if NUM_PAIRS_TO_PROCESS is not None:
        pairs = pairs[:NUM_PAIRS_TO_PROCESS]
    if not pairs:
        print("No pairs to process after SKIP_FIRST / limit.")
        return

    print(f"Processing {len(pairs)} matched regular <-> cute concept image pair(s).")
    for pair in pairs:
        print(f"   -> img_{pair.index}: {pair.regular_path.name} <-> {pair.cute_path.name}")

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [process_pair(pair, sem=sem) for pair in pairs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    failures = 0
    for pair, result in zip(pairs, results):
        if isinstance(result, Exception):
            failures += 1
            print(f"[img_{pair.index}] WARN {type(result).__name__}: {result}")

    expected_videos = len(pairs) * 2
    if failures:
        print(f"Done with {failures}/{len(pairs)} pair failure(s).")
    else:
        print(f"Done. Saved {expected_videos} videos to {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
