# Repository Guidelines

## Project Structure & Module Organization

This repository is a small static web app. The main application lives in `index.html`, which contains the markup, CSS, and JavaScript for the clock overlay and command input. The primary image asset is `succubus_anchor_01_4x4/anchor.png`. Additional generated image variants belong in `variations/` as `.png` files. Other local image-generation folders are intentionally ignored unless explicitly added to `.gitignore`.

## Build, Test, and Development Commands

There is no package manager or build step. Open the app directly in a browser:

```powershell
Start-Process .\index.html
```

For a local HTTP preview, use any simple static server from the repository root, for example:

```powershell
python -m http.server 8000
```

Then visit `http://localhost:8000/`. Use `git status` before and after edits to confirm only intended files changed.

## Coding Style & Naming Conventions

Keep this project dependency-free unless a feature clearly requires tooling. Use two-space indentation in HTML, CSS, and JavaScript to match `index.html`. Prefer semantic HTML, accessible labels, and visible focus states for interactive elements. Use lower-case, hyphenated CSS class names such as `.image-stage` and `.command-line`. Keep JavaScript functions small and named by behavior, for example `updateClock()`.

## Testing Guidelines

No automated test framework is configured. Manually verify changes in a browser at desktop and mobile-sized viewports. Confirm that the clock updates once per second, the image loads from `succubus_anchor_01_4x4/anchor.png`, the command input remains usable, and Tab completion still works for commands such as `clock`, `date`, and `help`. For visual changes, check that text remains readable over the image and focus outlines are visible.

## Commit & Pull Request Guidelines

Recent commits use short, imperative subjects, for example `Add initial succubus clock app` and `Make clock text keyboard focusable`. Follow that style: start with a verb, keep the subject concise, and describe one coherent change per commit.

Pull requests should include a brief summary, manual test notes, and screenshots or screen recordings for visual changes. Link related issues when available. Avoid committing generated or experimental assets unless they are referenced by the app or intentionally preserved in `variations/`.

## Security & Configuration Tips

Do not add secrets, API keys, or machine-specific paths. Keep `.gitignore` restrictive so only intentional app files and selected `.png` assets are tracked.
