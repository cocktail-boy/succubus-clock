"""
Async batch idle-animation Image-to-Video runner for:
  fal-ai/bytedance/seedance/v1.5/pro/image-to-video

For the anchor image and every PNG in ./variations, generate four separate idle
video sets:
  1. regular subtle idle
  2. natural eye blink idle
  3. succubus looks at viewer and leans her body forward
  4. succubus slowly traces her body contour teasingly
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fal_client
import requests

MODEL = "fal-ai/bytedance/seedance/v1.5/pro/image-to-video"

ANCHOR_IMAGE = Path("succubus_anchor_01_4x4") / "anchor.png"
VARIATIONS_DIR = Path("variations")
OUTPUT_ROOT = Path("video_outputs_seedance_1_5_pro")

PROMPT_SETS = [
    {
        "name": "idle_animations",
        "suffix": "idle",
        "prompt": (
            "Create a subtle looping video game idle animation from the provided image. "
            "Use gentle breathing motion, tiny posture shifts, slight hair and cloth movement, "
            "and a steady locked camera. Preserve the character, composition, colors, and painterly style. "
            "The first and last frames should match closely for a seamless idle loop. "
            "Avoid walking, posing changes, scene changes, jitter, warping, flicker, extra limbs, "
            "distorted hands, or facial deformation."
        ),
    },
    {
        "name": "idle_blink_animations",
        "suffix": "idle_blink",
        "prompt": (
            "Create a subtle looping video game idle animation from the provided image. "
            "Use gentle breathing motion, tiny posture shifts, slight hair and cloth movement, "
            "and one or two natural soft eye blinks. Keep the eyelids realistic and symmetrical, "
            "with no change to gaze direction or facial identity. Preserve the character, composition, "
            "colors, and painterly style. The first and last frames should match closely for a seamless "
            "idle loop. Avoid walking, posing changes, scene changes, jitter, warping, flicker, extra limbs, "
            "distorted hands, facial deformation, or exaggerated cartoon blinking."
        ),
    },
    {
        "name": "idle_look_forward",
        "suffix": "idle_look_forward",
        "prompt": (
            "Create a subtle looping video game idle animation from the provided image. "
            "The succubus keeps warm eye contact with the viewer and slowly leans her body forward, "
            "with gentle breathing, tiny posture shifts, slight hair and cloth movement, and a steady locked camera. "
            "Preserve the character, composition, colors, and painterly style. The first and last frames should "
            "match closely for a seamless idle loop. Avoid walking, major posing changes, scene changes, jitter, "
            "warping, flicker, extra limbs, distorted hands, facial deformation, or identity drift."
        ),
    },
    {
        "name": "idle_body_trace",
        "suffix": "idle_body_trace",
        "prompt": (
            "Create a subtle looping video game idle animation from the provided image. "
            "The succubus slowly traces her body contour teasingly with graceful, restrained hand movement, "
            "while maintaining gentle breathing, tiny posture shifts, slight hair and cloth movement, and a steady locked camera. "
            "Keep the motion elegant and natural, without changing the pose or outfit. Preserve the character, composition, "
            "colors, and painterly style. The first and last frames should match closely for a seamless idle loop. "
            "Avoid walking, major posing changes, scene changes, jitter, warping, flicker, extra limbs, distorted hands, "
            "facial deformation, or identity drift."
        ),
    },
]

RESOLUTION = "720p"
ASPECT_RATIO = "auto"
IDLE_DURATION = 4
CAMERA_FIXED = True
ENABLE_SAFETY_CHECKER = False
GENERATE_AUDIO = False
SEED = -1
CONCURRENCY = 20

INCLUDE_ANCHOR = True
SKIP_FIRST = 0
NUM_FILES_TO_PROCESS: Optional[int] = None

_ALLOWED_ASPECTS = {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "auto"}
_ALLOWED_RES = {"480p", "720p", "1080p"}
_ALLOWED_DUR = set(range(4, 13))


def _validate_config() -> None:
    if ASPECT_RATIO not in _ALLOWED_ASPECTS:
        raise ValueError(f"ASPECT_RATIO must be one of {sorted(_ALLOWED_ASPECTS)}; got {ASPECT_RATIO!r}")
    if RESOLUTION not in _ALLOWED_RES:
        raise ValueError(f"RESOLUTION must be one of {sorted(_ALLOWED_RES)}; got {RESOLUTION!r}")
    if IDLE_DURATION not in _ALLOWED_DUR:
        raise ValueError(f"IDLE_DURATION must be one of {sorted(_ALLOWED_DUR)}; got {IDLE_DURATION!r}")
    if SKIP_FIRST < 0:
        raise ValueError(f"SKIP_FIRST must be >= 0; got {SKIP_FIRST!r}")
    if NUM_FILES_TO_PROCESS is not None and NUM_FILES_TO_PROCESS < 1:
        raise ValueError(f"NUM_FILES_TO_PROCESS must be >= 1 or None; got {NUM_FILES_TO_PROCESS!r}")
    if INCLUDE_ANCHOR and not ANCHOR_IMAGE.exists():
        raise FileNotFoundError(f"Anchor image not found: {ANCHOR_IMAGE.resolve()}")
    if not VARIATIONS_DIR.exists():
        raise FileNotFoundError(f"Variations directory not found: {VARIATIONS_DIR.resolve()}")
    for prompt_set in PROMPT_SETS:
        if not prompt_set["name"].strip():
            raise ValueError("Each prompt set needs a non-empty name")
        if not prompt_set["suffix"].strip():
            raise ValueError(f"Prompt set {prompt_set['name']!r} needs a non-empty suffix")
        if not prompt_set["prompt"].strip():
            raise ValueError(f"Prompt set {prompt_set['name']!r} needs a non-empty prompt")


def image_jobs() -> List[Tuple[str, Path]]:
    jobs: List[Tuple[str, Path]] = []
    if INCLUDE_ANCHOR:
        jobs.append(("anchor", ANCHOR_IMAGE))

    for variation_path in sorted(VARIATIONS_DIR.glob("*.png")):
        jobs.append((variation_path.stem, variation_path))

    return sorted(jobs, key=lambda item: str(item[1]))


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
    prompt: str,
    image_url: str,
    out_path: Path,
) -> None:
    print(f"[{label}] submitting {IDLE_DURATION}s idle animation...")

    input_payload: Dict[str, Any] = {
        "prompt": prompt,
        "image_url": image_url,
        "end_image_url": image_url,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "duration": IDLE_DURATION,
        "camera_fixed": CAMERA_FIXED,
        "seed": SEED,
        "enable_safety_checker": ENABLE_SAFETY_CHECKER,
        "generate_audio": GENERATE_AUDIO,
    }

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


async def process_image(
    name: str,
    image_path: Path,
    *,
    prompt_set: Dict[str, str],
    sem: asyncio.Semaphore,
) -> None:
    async with sem:
        output_dir = OUTPUT_ROOT / prompt_set["name"]
        out_path = output_dir / f"{name}_{prompt_set['suffix']}_{IDLE_DURATION}s.mp4"
        if out_path.exists():
            print(f"[{prompt_set['name']} / {name}] already done, skipping.")
            return

        print(f"[{prompt_set['name']} / {name}] uploading source image...")
        image_url = await fal_client.upload_file_async(str(image_path))
        await generate_idle_video(
            label=f"{prompt_set['name']} / {name}",
            prompt=prompt_set["prompt"],
            image_url=image_url,
            out_path=out_path,
        )


async def run_prompt_set(prompt_set: Dict[str, str], jobs: List[Tuple[str, Path]]) -> int:
    output_dir = OUTPUT_ROOT / prompt_set["name"]
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Processing {len(jobs)} image job(s) for {prompt_set['name']}.")
    for name, image_path in jobs:
        print(f"   -> {name}: {image_path}")

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [process_image(name, image_path, prompt_set=prompt_set, sem=sem) for name, image_path in jobs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    failures = 0
    for (name, _image_path), result in zip(jobs, results):
        if isinstance(result, Exception):
            failures += 1
            print(f"[{prompt_set['name']} / {name}] WARN {type(result).__name__}: {result}")

    if failures:
        print(f"{prompt_set['name']} done with {failures}/{len(jobs)} failure(s).")
    else:
        print(f"{prompt_set['name']} done. Saved videos to {output_dir.resolve()}")
    return failures


async def main() -> None:
    _validate_config()

    all_jobs = image_jobs()
    if not all_jobs:
        print("No idle animation image jobs found.")
        return

    jobs = all_jobs[SKIP_FIRST:]
    if NUM_FILES_TO_PROCESS is not None:
        jobs = jobs[:NUM_FILES_TO_PROCESS]
    if not jobs:
        print("No idle animation jobs to process after SKIP_FIRST / limit.")
        return

    total_failures = 0
    for prompt_set in PROMPT_SETS:
        total_failures += await run_prompt_set(prompt_set, jobs)

    if total_failures:
        print(f"Done with {total_failures} total failure(s).")
    else:
        print("Done. Both prompt sets completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
