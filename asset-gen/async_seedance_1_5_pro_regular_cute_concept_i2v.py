"""
Seedance 1.5 Pro regular <-> cute concept transition runner.

Uses the same image pairing logic as async_seedance_2_0_regular_cute_concept_i2v.py,
but sends the Seedance 1.5 Pro image-to-video request schema.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

import fal_client

import async_seedance_2_0_regular_cute_concept_i2v as base

MODEL = "fal-ai/bytedance/seedance/v1.5/pro/image-to-video"

OUTPUT_DIR = Path("video_outputs_seedance_1_5_pro") / "regular_cute_concept_transitions"
PROMPT = base.PROMPT

RESOLUTION = "720p"
ASPECT_RATIO = "auto"
DURATION = 4
CAMERA_FIXED = True
ENABLE_SAFETY_CHECKER = False
GENERATE_AUDIO = False
SEED = -1
CONCURRENCY = 20

SKIP_FIRST = 0
NUM_PAIRS_TO_PROCESS: Optional[int] = None

_ALLOWED_ASPECTS = {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "auto"}
_ALLOWED_RES = {"480p", "720p", "1080p"}
_ALLOWED_DUR = set(range(4, 13))


def _validate_config() -> None:
    if ASPECT_RATIO not in _ALLOWED_ASPECTS:
        raise ValueError(f"ASPECT_RATIO must be one of {sorted(_ALLOWED_ASPECTS)}; got {ASPECT_RATIO!r}")
    if RESOLUTION not in _ALLOWED_RES:
        raise ValueError(f"RESOLUTION must be one of {sorted(_ALLOWED_RES)}; got {RESOLUTION!r}")
    if DURATION not in _ALLOWED_DUR:
        raise ValueError(f"DURATION must be one of {sorted(_ALLOWED_DUR)}; got {DURATION!r}")
    if not PROMPT.strip():
        raise ValueError("PROMPT must be a non-empty string")
    if NUM_PAIRS_TO_PROCESS is not None and NUM_PAIRS_TO_PROCESS < 1:
        raise ValueError(f"NUM_PAIRS_TO_PROCESS must be >= 1 or None; got {NUM_PAIRS_TO_PROCESS!r}")
    if SKIP_FIRST < 0:
        raise ValueError(f"SKIP_FIRST must be >= 0; got {SKIP_FIRST!r}")
    if not base.REGULAR_VARIATIONS_DIR.exists():
        raise FileNotFoundError(f"Regular variations directory not found: {base.REGULAR_VARIATIONS_DIR.resolve()}")
    if not base.CUTE_VARIATIONS_DIR.exists():
        raise FileNotFoundError(f"Cute concept variations directory not found: {base.CUTE_VARIATIONS_DIR.resolve()}")


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
        "camera_fixed": CAMERA_FIXED,
        "seed": SEED,
        "enable_safety_checker": ENABLE_SAFETY_CHECKER,
        "generate_audio": GENERATE_AUDIO,
    }

    handler = await fal_client.submit_async(MODEL, arguments=input_payload)
    result: Dict[str, Any] = await handler.get()
    video_url = base.get_video_url(result)
    if not video_url:
        raise ValueError(f"[{label}] No video URL in result: {result}")

    await asyncio.to_thread(base.download, video_url, out_path)
    print(f"[{label}] OK saved -> {out_path}")


async def process_pair(pair: base.ImagePair, *, sem: asyncio.Semaphore) -> None:
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

        jobs = (
            (f"{stem} regular->cute concept", regular_url, cute_url, regular_to_cute_out),
            (f"{stem} cute concept->regular", cute_url, regular_url, cute_to_regular_out),
        )
        for label, start_url, end_url, out_path in jobs:
            if out_path.exists():
                print(f"[{label}] already exists, skipping.")
                continue
            try:
                await generate_video(
                    label=label,
                    start_image_url=start_url,
                    end_image_url=end_url,
                    out_path=out_path,
                )
            except Exception as exc:
                print(f"[{label}] WARN {type(exc).__name__}: {exc}")


async def main() -> None:
    _validate_config()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_pairs = base._build_pairs()
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
    await asyncio.gather(*(process_pair(pair, sem=sem) for pair in pairs))


if __name__ == "__main__":
    asyncio.run(main())
