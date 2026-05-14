"""
Seedance 1.5 pro transition runner for close-up seduction variations.

For every PNG in ./variations_closeup_seduction, generate:
  1. anchor -> variation, 8 seconds
  2. variation -> anchor, 4 seconds
"""

import asyncio
from pathlib import Path

import async_seedance_1_5_pro_dwz_variations_i2v as runner

runner.VARIATIONS_DIR = Path("variations_closeup_seduction")
runner.OUTPUT_DIR = Path("video_outputs_seedance_1_5_pro") / "anchor_variations_closeup_seduction"
runner.PROMPT = (
    "Preserve the character identity, close-up composition, colors, and painterly style. "
    "Create a smooth cinematic transition between the provided start and end frames, "
    "with gentle natural body motion, subtle hair movement, warm eye contact, and a steady locked camera. "
    "Keep the motion alluring, elegant, and non-explicit. Avoid jitter, warping, flicker, extra limbs, "
    "distorted hands, facial deformation, or sudden scene changes."
)


if __name__ == "__main__":
    asyncio.run(runner.main())
