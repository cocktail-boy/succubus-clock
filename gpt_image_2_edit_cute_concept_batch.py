"""
Batch image-edit for openai/gpt-image-2/edit: convert every image under
INPUT_ROOT into a super-cute stylized character illustration in the style of
high-end western video game concept art (NOT anime / manga).

Input folder matches the output subdir from gpt_image_2_edit_variations.py.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import fal_client

import fal_lib

ImageSize = Union[str, Dict[str, int]]

fal_lib.setup_utf8_console()

# ---- Config ----
MODEL = "openai/gpt-image-2/edit"

INPUT_ROOT = Path("./variations")
OUTPUT_ROOT = Path("./variations_cute_concept")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

EDIT_PROMPT = (
    "Transform this image into a super cute, stylized character illustration in the style of "
    "high-end western video game concept art and character design sheets (think modern Blizzard, "
    "Riot, Supergiant, Pixar / DreamWorks key art) — explicitly NOT anime or manga. "
    "Preserve the subject's identity, pose, composition, and framing. "
    "Use appealing shape language with slightly chibi-leaning proportions: a softly rounded head, "
    "large expressive eyes with painted irises, small button-like nose, soft cheeks, and a warm "
    "friendly expression. Keep clean readable silhouette, polished hand-painted rendering, "
    "saturated yet harmonious colors, soft volumetric lighting with gentle rim light, "
    "and subtle painterly brush texture. "
    "Strictly avoid anime / manga conventions: no flat cel shading, no sharp pointy anime chin, "
    "no oversized sparkle catchlights or tear-drop highlights, no manga screentone, no inked "
    "outline linework, no anime hair spikes. Aim for a charming, approachable, lovable "
    "high-quality video game concept art look."
)

IMAGE_SIZE: ImageSize = {"width": 720, "height": 1280}
QUALITY = "medium"
OUTPUT_FORMAT = "png"
NUM_IMAGES_PER_SOURCE = 1
API_MAX_NUM_IMAGES = 4
CONCURRENCY = 10

# When True, skip API calls if expected output file(s) for that source already exist.
SKIP_IF_OUTPUT_EXISTS = True

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
    if NUM_IMAGES_PER_SOURCE < 1:
        raise ValueError("NUM_IMAGES_PER_SOURCE must be >= 1")
    if API_MAX_NUM_IMAGES < 1:
        raise ValueError("API_MAX_NUM_IMAGES must be >= 1")


def _non_clobber_path(path: Path) -> Path:
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


def collect_images(root: Path) -> List[Path]:
    if not root.is_dir():
        raise FileNotFoundError(f"INPUT_ROOT is not a directory: {root.resolve()}")
    out: List[Path] = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            # Resolve so relative_to(input_root) works when input_root is absolute.
            out.append(p.resolve())
    return out


def make_payload(prompt: str, image_url: str, num_images: int) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "prompt": prompt,
        "image_urls": [image_url],
        "image_size": IMAGE_SIZE,
        "quality": QUALITY,
        "num_images": num_images,
        "output_format": OUTPUT_FORMAT,
    }
    if BYOK_OPENAI_API_KEY:
        payload["openai_api_key"] = BYOK_OPENAI_API_KEY
    return payload


def _slot_output_exists(base_dir: Path, stem: str, slot: int) -> bool:
    primary = base_dir / f"{stem}_cute_concept_{slot:02d}.{OUTPUT_FORMAT}"
    if primary.is_file():
        return True
    pattern = f"{stem}_cute_concept_{slot:02d}_r*.{OUTPUT_FORMAT}"
    return any(p.is_file() for p in base_dir.glob(pattern))


def source_outputs_complete(source_path: Path, input_root: Path, output_root: Path) -> bool:
    rel = source_path.relative_to(input_root)
    base_dir = output_root / rel.parent
    stem = rel.stem
    return all(_slot_output_exists(base_dir, stem, i) for i in range(1, NUM_IMAGES_PER_SOURCE + 1))


def dest_paths_for_source(
    source_path: Path,
    *,
    input_root: Path,
    output_root: Path,
    num_saved: int,
    num_urls: int,
) -> List[Path]:
    """One output path per generated image, preserving relative dirs under output_root."""
    rel = source_path.relative_to(input_root)
    base_dir = output_root / rel.parent
    stem = rel.stem
    paths: List[Path] = []
    for i in range(num_urls):
        idx = num_saved + i + 1
        name = f"{stem}_cute_concept_{idx:02d}.{OUTPUT_FORMAT}"
        paths.append(base_dir / name)
    return paths


async def process_one_image(
    source_path: Path,
    *,
    input_root: Path,
    output_root: Path,
    sem: asyncio.Semaphore,
) -> Tuple[int, int]:
    """Returns (newly_saved_count, skipped_existing_count)."""
    tag = str(source_path.relative_to(input_root))
    if SKIP_IF_OUTPUT_EXISTS and source_outputs_complete(source_path, input_root, output_root):
        print(f"[{tag}] skip (output already present)", flush=True)
        return (0, NUM_IMAGES_PER_SOURCE)

    async with sem:
        print(f"[{tag}] uploading...", flush=True)
        try:
            image_url = await fal_client.upload_file_async(str(source_path.resolve()))
        except Exception as exc:
            print(f"[{tag}] upload FAIL: {fal_lib.short_exc(exc)}", flush=True)
            return (0, 0)

        target = NUM_IMAGES_PER_SOURCE
        saved = 0
        req_count = (target + API_MAX_NUM_IMAGES - 1) // API_MAX_NUM_IMAGES

        for req_i in range(1, req_count + 1):
            req_n = min(API_MAX_NUM_IMAGES, target - saved)
            if req_n <= 0:
                break

            rtag = f"{tag} r{req_i}"
            print(f"[{tag}] submit r{req_i} ({req_n} image(s))...", flush=True)
            try:
                result = await fal_lib.submit_and_get(
                    MODEL, make_payload(EDIT_PROMPT, image_url, req_n), log_tag=rtag,
                )
                images = fal_lib.extract_images(result)
                if not images:
                    raise ValueError("No image URLs in response result")

                dests = dest_paths_for_source(
                    source_path,
                    input_root=input_root,
                    output_root=output_root,
                    num_saved=saved,
                    num_urls=len(images),
                )
                for img, dest in zip(images, dests):
                    out_path = _non_clobber_path(dest)
                    await fal_lib.download_async(img["url"], out_path)
                    print(f"[{tag}] saved -> {out_path}", flush=True)
                saved += len(images)
            except Exception as exc:
                print(f"[{tag}] r{req_i} FAIL: {fal_lib.short_exc(exc)}", flush=True)

        print(f"[{tag}] done {saved}/{target}", flush=True)
        return (saved, 0)


async def main() -> None:
    _validate_config()
    input_root = INPUT_ROOT.resolve()
    output_root = OUTPUT_ROOT.resolve()
    sources = collect_images(INPUT_ROOT)
    if not sources:
        raise FileNotFoundError(
            f"No images found under {INPUT_ROOT.resolve()} "
            f"(extensions {sorted(IMAGE_EXTENSIONS)})"
        )

    output_root.mkdir(parents=True, exist_ok=True)

    size_repr = IMAGE_SIZE if isinstance(IMAGE_SIZE, str) else f"{IMAGE_SIZE['width']}x{IMAGE_SIZE['height']}"
    total_target = len(sources) * NUM_IMAGES_PER_SOURCE
    print(f"Cute concept-art batch: {len(sources)} source image(s), model {MODEL}", flush=True)
    print(f"Input:  {input_root}", flush=True)
    print(f"Output: {output_root}", flush=True)
    print(f"Size: {size_repr} | Quality: {QUALITY} | Format: {OUTPUT_FORMAT}", flush=True)
    print(f"Concurrency: {CONCURRENCY} | skip_if_output_exists={SKIP_IF_OUTPUT_EXISTS}", flush=True)
    print(flush=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        process_one_image(p, input_root=input_root, output_root=output_root, sem=sem)
        for p in sources
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    saved_total = 0
    skipped_total = 0
    crashed = 0
    for r in results:
        if isinstance(r, Exception):
            crashed += 1
        else:
            s, sk = r
            saved_total += s
            skipped_total += sk

    accounted = saved_total + skipped_total
    missing = total_target - accounted

    print(flush=True)
    print(
        f"New downloads: {saved_total}, skipped (already on disk): {skipped_total} "
        f"-> {accounted}/{total_target} under {output_root}",
        flush=True,
    )
    if missing > 0:
        print(
            f"Still missing {missing} image(s); re-run the script to retry "
            f"(skips existing when enabled).",
            flush=True,
        )
    if crashed:
        print(f"Tasks crashed unexpectedly: {crashed}/{len(sources)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
