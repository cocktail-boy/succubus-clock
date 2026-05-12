# Variation pipeline — image prompts to playing in the app

Reference for adding a new set of succubus variations end-to-end. The dwz set is the canonical recent example; substitute your own set name (e.g. `dwz`, `seasonal`) anywhere `dwz` appears.

The flow has four phases. Each phase has a script in the project root.

---

## Phase 1 — Image prompts (text file)

Format: a single text file at the project root with two sections delimited by 64-`=` rule lines:

1. `CHARACTER SHEET (paste verbatim into every prompt)` — describes the consistent identity (face, horns, outfit, wings) so every variation looks like the same character.
2. `VARIATION PROMPTS` — numbered `--- NN. Title ---` blocks. Each body contains the literal token `[CHARACTER SHEET]`, which the generator script substitutes before sending to the API.

Canonical examples:
- `succubus_diewithzero_variations.txt` (6 dwz variations)
- `succubus_20_variations.txt` (the original 20, lives in `e:\fal-image-generation\prompt_files\`)

Style note (saved in memory): no smoke in prompts — embers only. Past glyph runs with smoke looked bad.

---

## Phase 2 — GPT Image 2 generation

Script: `gpt_image_2_edit_dwz_variations.py`

- Model: `openai/gpt-image-2/edit`
- Anchor: `succubus_anchor_01_4x4/anchor.png` (passed as `image_urls[0]` reference)
- Prompts: parsed from the Phase 1 text file via `_extract_between_markers`
- Output: `succubus_variations_diewithzero/variation_NN/succubus_dwz_vNN_MM.png` (4 candidates per variation by default; `NUM_IMAGES_PER_VARIATION = 4`)
- Size/quality: 720×1280, medium, png

Manual step after generation:
1. Pick the best candidate from each `variation_NN/` folder.
2. Copy picks into a flat `variations_diewithzero/` folder at project root.
3. Drop the `_MM` sub-index from filenames so they end at `succubus_dwz_vNN.png`. The downstream seedance scripts glob this folder.

Run: `python gpt_image_2_edit_dwz_variations.py`

---

## Phase 3 — Seedance 1.5 pro video generation

Two scripts run sequentially, both reading from `variations_diewithzero/`:

### 3a. Anchor ↔ variation transitions
Script: `async_seedance_1_5_pro_dwz_variations_i2v.py`

For every PNG in `variations_diewithzero/`, generates two clips:
- **Forward** (anchor → variation, 8s) — `succubus_dwz_vNN_anchor_to_variation_8s.mp4`
- **Return** (variation → anchor, 4s) — `succubus_dwz_vNN_variation_to_anchor_4s.mp4`

Output: `video_outputs_seedance_1_5_pro/anchor_variations_diewithzero/`

### 3b. Idle prompt sets
Script: `async_seedance_1_5_pro_dwz_idle_prompt_sets_i2v.py`

For every variation PNG (anchor excluded — its idles already exist from the original run), generates 4 idle types × 4 seconds each:
- `idle_animations_diewithzero/` — regular subtle idle
- `idle_blink_animations_diewithzero/` — natural eye blink
- `idle_look_forward_diewithzero/` — leans forward with eye contact
- `idle_body_trace_diewithzero/` — traces body contour teasingly

Filename pattern: `succubus_dwz_vNN_<suffix>_4s.mp4` per variation per set.

### 3c. HandBrake compression
Run: `.\compress_videos_handbrake.ps1`

The PS1 walks `video_outputs_seedance_1_5_pro/` recursively and writes to `video_outputs_seedance_1_5_pro_handbrake/` with the same subdir structure. Settings: x264 medium, quality 28, 24fps CFR, audio stripped. Typical savings: ~88%. Already-compressed files are skipped without `-Force`.

---

## Phase 4 — HTML app integration

Two files to edit:

### 4a. `index.html` — variation rotation

The `successfulVariations` array drives the rotation. Each entry is `{ id, subdir }`:

```js
const successfulVariations = [
  { id: 'succubus_dwz_v01', subdir: '_diewithzero' },
  // ... add more here, in the order they should appear
  { id: 'img_0001', subdir: '' },
  // legacy entries with empty subdir
];
```

The map builder resolves paths as `${basePath}${subdir}/${id}_..._4s.mp4`, so each subdir (`anchor_variations`, `idle_animations`, etc.) needs to physically exist with the matching suffix on disk. Array order is rotation order — put new variations first if you want them to play first.

Anchor idles are separate constants (`anchorIdleVideo` etc.) and don't need touching when adding new variations.

### 4b. `sw.js` — service worker cache

Two updates required:
- Add each new compressed subdir path to `MEDIA_PATHS` (with trailing slash; the matcher uses `startsWith`). `anchor_variations_diewithzero/` does NOT match an existing entry for `anchor_variations/`.
- Bump `CACHE_NAME` version (e.g. `v16` → `v17`) so existing clients drop the old cache and refetch the updated allowlist.

---

## Phase 5 — Git tracking

`.gitignore` is allowlist-based (`*` ignores everything; `!` un-ignores). For each new compressed subdir, add three lines following the existing pattern:

```
!video_outputs_seedance_1_5_pro_handbrake/<subdir>/
video_outputs_seedance_1_5_pro_handbrake/<subdir>/*
!video_outputs_seedance_1_5_pro_handbrake/<subdir>/*.mp4
```

Source scripts and the prompts text file also need `!script_name.py` entries to be tracked.

Then stage and commit: scripts + prompts file + index/sw changes + all `.mp4`s under each new subdir.
