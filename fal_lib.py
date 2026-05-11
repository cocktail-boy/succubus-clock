"""
Shared utilities for the fal.ai batch generation scripts in this repo.

Scripts keep their own top-of-file config block, payload builders, and
per-task async functions. This module covers the duplicated infrastructure:

  setup_utf8_console()           Windows cp1252 -> utf-8 stdout/stderr
  download(url, dest)            stream a URL to disk
  download_async(url, dest)      asyncio.to_thread wrapper around download()
  short_exc(exc)                 truncated str(exc) suitable for logs
  safe_basename(name)            sanitize an API-supplied file_name (no traversal)
  extract_images(result)         list of image dicts, robust to SDK wrappers
  extract_video_url(result)      video URL string, robust to SDK wrappers
  submit_and_get(model, payload) submit_async + iter_events status logging + get
  slugify(name)                  filename-safe character slug
  load_character_prompts(path)   parse "--- Name ---" prompt files into entries

See prototype_gpt_image_2_generator.py and prototype_async_seedance_v1_5_loop.py
for usage examples.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fal_client
import requests

PromptEntry = Tuple[str, str, str]


def setup_utf8_console(*, line_buffering: bool = False) -> None:
    """Reconfigure stdout/stderr to UTF-8 (Windows consoles default to cp1252).

    Pass ``line_buffering=True`` to also flush after every newline so
    print(..., flush=True) is reliable in piped/captured stdout.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                kw: Dict[str, Any] = {"encoding": "utf-8", "errors": "replace"}
                if line_buffering:
                    kw["line_buffering"] = True
                stream.reconfigure(**kw)
            except (OSError, ValueError, AttributeError, TypeError):
                pass


def download(url: str, dest: Path, *, timeout: int = 180, chunk_bytes: int = 1024 * 1024) -> None:
    """Stream-download a URL to dest (creates parent dirs)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_bytes):
                if chunk:
                    f.write(chunk)


async def download_async(url: str, dest: Path, **kw: Any) -> None:
    await asyncio.to_thread(download, url, dest, **kw)


def short_exc(exc: BaseException, max_len: int = 700) -> str:
    """Readable one-line-ish error for logs; truncates noisy API payloads."""
    s = f"{type(exc).__name__}: {exc}"
    return s if len(s) <= max_len else s[: max_len - 1] + "..."


def safe_basename(file_name: str) -> str:
    """Use an API-supplied file_name as a single path segment (no dirs, no traversal)."""
    base = Path(file_name).name.strip()
    if not base or base in (".", ".."):
        raise ValueError(f"Invalid API file_name: {file_name!r}")
    return base


def extract_images(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Image dicts from a fal result, robust to the {'data': {...}} wrapper."""
    images = result.get("images") or []
    if not images:
        data = result.get("data")
        if isinstance(data, dict):
            images = data.get("images") or []
    return [img for img in images if isinstance(img, dict) and img.get("url")]


def extract_video_url(result: Dict[str, Any]) -> Optional[str]:
    """Video URL from a fal result; tries video.url and video_url at root and .data."""
    candidates: List[Dict[str, Any]] = [result]
    data = result.get("data")
    if isinstance(data, dict):
        candidates.append(data)
    for root in candidates:
        v = root.get("video")
        if isinstance(v, dict) and isinstance(v.get("url"), str):
            return v["url"]
        if isinstance(root.get("video_url"), str):
            return root["video_url"]
    return None


async def submit_and_get(
    model: str,
    payload: Dict[str, Any],
    *,
    log_tag: Optional[str] = None,
    with_logs: bool = False,
) -> Dict[str, Any]:
    """
    Submit a fal job, optionally print queue status events under [log_tag],
    return the final result dict.
    """
    handler = await fal_client.submit_async(model, arguments=payload)
    async for event in handler.iter_events(with_logs=with_logs):
        status = getattr(event, "status", None)
        if status and log_tag:
            print(f"[{log_tag}] {status}", flush=True)
    return await handler.get()


_SECTION_HEADER = re.compile(r"^---\s*(.+?)\s*---\s*$", re.MULTILINE)


def slugify(name: str) -> str:
    """Filename-safe character slug; raises if the result is empty."""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[-\s]+", "_", s).strip("_")
    if not s:
        raise ValueError(f"Invalid character name for folder slug: {name!r}")
    return s


def load_character_prompts(path: Path) -> List[PromptEntry]:
    """
    Parse a character-prompts file into (slug, display_name, prompt) tuples.

    File format:
      --- Character Name ---
      <prompt body, blank lines allowed>
      --- Next Character ---
      <prompt body>
    """
    if not path.is_file():
        raise FileNotFoundError(f"Prompts file not found: {path.resolve()}")

    text = path.read_text(encoding="utf-8")
    chunks = _SECTION_HEADER.split(text)
    if chunks and chunks[0].strip():
        raise ValueError(
            f"Prompts file must start with --- Character Name ---; "
            f"found text before first header: {path}"
        )

    out: List[PromptEntry] = []
    i = 1
    while i < len(chunks):
        display_name = chunks[i].strip()
        body = chunks[i + 1].strip() if i + 1 < len(chunks) else ""
        if not display_name:
            i += 2
            continue
        if not body:
            raise ValueError(f"Empty prompt body for character {display_name!r} in {path}")
        out.append((slugify(display_name), display_name, body))
        i += 2

    if not out:
        raise ValueError(f"No character sections found in {path} (use --- Name --- headers)")
    return out
