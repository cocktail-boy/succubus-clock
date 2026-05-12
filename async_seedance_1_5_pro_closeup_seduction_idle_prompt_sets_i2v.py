"""
Seedance 1.5 pro idle-animation runner for close-up seduction variations.

For every PNG in ./variations_closeup_seduction, generate four separate
idle video sets tuned for tight alluring portrait shots.
"""

import asyncio
from pathlib import Path

import async_seedance_1_5_pro_dwz_idle_prompt_sets_i2v as runner

runner.VARIATIONS_DIR = Path("variations_closeup_seduction")
runner.PROMPT_SETS = [
    {
        "name": "idle_animations_closeup_seduction",
        "suffix": "idle",
        "prompt": (
            "Create a subtle looping close-up video game idle animation from the provided image. "
            "Use gentle breathing motion, tiny posture shifts, slight hair movement, and a steady locked camera. "
            "Preserve the character identity, close-up composition, colors, and painterly style. "
            "The first and last frames should match closely for a seamless idle loop. "
            "Avoid walking, pose changes, scene changes, jitter, warping, flicker, extra limbs, "
            "distorted hands, facial deformation, or identity drift."
        ),
    },
    {
        "name": "idle_blink_animations_closeup_seduction",
        "suffix": "idle_blink",
        "prompt": (
            "Create a subtle looping close-up video game idle animation from the provided image. "
            "Use gentle breathing motion, tiny posture shifts, slight hair movement, and one or two natural soft eye blinks. "
            "Keep the eyelids realistic and symmetrical, with no change to gaze direction or facial identity. "
            "Preserve the character identity, close-up composition, colors, and painterly style. "
            "The first and last frames should match closely for a seamless idle loop. "
            "Avoid pose changes, scene changes, jitter, warping, flicker, extra limbs, distorted hands, "
            "facial deformation, exaggerated blinking, or identity drift."
        ),
    },
    {
        "name": "idle_look_forward_closeup_seduction",
        "suffix": "idle_look_forward",
        "prompt": (
            "Create a subtle looping close-up video game idle animation from the provided image. "
            "The succubus keeps warm eye contact with the viewer and slowly leans a little closer, "
            "with gentle breathing, tiny posture shifts, slight hair movement, and a steady locked camera. "
            "Keep the motion alluring, elegant, and non-explicit. Preserve the character identity, close-up composition, "
            "colors, and painterly style. The first and last frames should match closely for a seamless idle loop. "
            "Avoid major pose changes, scene changes, jitter, warping, flicker, extra limbs, distorted hands, "
            "facial deformation, or identity drift."
        ),
    },
    {
        "name": "idle_body_trace_closeup_seduction",
        "suffix": "idle_body_trace",
        "prompt": (
            "Create a subtle looping close-up video game idle animation from the provided image. "
            "The succubus makes a restrained teasing gesture near her collarbone, choker, cheek, or hair, "
            "while maintaining gentle breathing, slight hair movement, and a steady locked camera. "
            "Keep the gesture graceful, tasteful, and non-explicit without changing the outfit or pose. "
            "Preserve the character identity, close-up composition, colors, and painterly style. "
            "The first and last frames should match closely for a seamless idle loop. "
            "Avoid major pose changes, scene changes, jitter, warping, flicker, extra limbs, distorted hands, "
            "facial deformation, or identity drift."
        ),
    },
]


if __name__ == "__main__":
    asyncio.run(runner.main())
