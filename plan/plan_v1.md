# Plan: Figma MCP Integration for Design-to-Website Visual Testing

## Overview

Build a Django-based testing system that compares your Figma designs against your live website to measure how closely the implementation matches the design. The system uses the **Figma MCP server** (or Figma REST API) to extract design screenshots/data, **Playwright** to capture live website screenshots, and **pixelmatch** to compute pixel-level visual diffs with a Design Fidelity Score.

**Project is greenfield** — the directory is currently empty (only this plan directory exists).

---

## Architecture

```
Figma Design (source of truth)
     │
     ▼
┌─────────────────────┐     ┌──────────────────────┐
│  Figma MCP Server   │     │  Live Django Website  │
│  - get_screenshot    │     │  (running locally)     │
│  - download_assets   │     └──────────┬───────────┘
│  - get_variable_defs │                │
│  - get_metadata      │                ▼
└──────────┬──────────┘     ┌──────────────────────┘
           │                │  Playwright           │
           ▼                │  Screenshot Capture    │
┌─────────────────────┐    └──────────┬───────────┘
│  Baseline Images     │                │
│  (Figma PNG exports) │                ▼
└──────────┬──────────┘     ┌──────────────────────┐
           │                │  Actual Screenshots   │
           ▼                └──────────┬───────────┘
┌──────────────────────────────────────┐
│       Comparison Engine               │
│  - pixelmatch (pixel diff)            │
│  - Design Fidelity Score (0-100%)     │
│  - Diff image generation              │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│  Django Admin + HTML Report           │
│  - View baselines, actuals, diffs     │
│  - Pass/fail history                  │
│  - Fidelity score tracking            │
└──────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Web Framework | Django 5.x | Project scaffold, admin UI, ORM models |
| Browser Automation | Playwright (Python) | Capture live website screenshots |
| Visual Comparison | pixelmatch + Pillow | Pixel-level diffing with anti-aliasing detection |
| Test Runner | pytest + pytest-django + pytest-playwright | Test orchestration and assertions |
| Figma Integration | Figma MCP server (remote) or Figma REST API | Extract design screenshots and metadata |
| MCP SDK | `mcp[cli]` Python SDK | Build custom MCP server exposing test tools to LLMs |
| Config | django-environ | Manage Figma tokens and env variables |

---

## Project Structure

```
django_qa_figma_testing/
├── manage.py
├── requirements.txt
├── .env                          # FIGMA_ACCESS_TOKEN, FIGMA_FILE_KEY
├── plan/                         # Planning documents
│   └── plan_v1.md                # This file
├── qa_figma/                     # Django project root
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py / asgi.py
├── figma_integration/            # App: Figma API client + MCP server
│   ├── models.py                 # DesignRef, TestRun, DiffResult models
│   ├── figma_client.py           # Figma REST API wrapper (fetch, export images)
│   ├── mcp_server.py             # FastMCP server exposing test tools to LLMs
│   └── management/commands/
│       └── sync_figma.py         # Import/sync designs from Figma
├── visual_tests/                 # App: Visual comparison engine
│   ├── comparators.py            # pixelmatch wrapper, fidelity score calc
│   ├── browser.py                # Playwright screenshot capture
│   └── tests/
│       ├── conftest.py           # pytest fixtures (figma baselines, browser)
│       ├── test_screenshot.py    # Screenshot capture tests
│       └── test_visual_diff.py   # Figma-vs-live comparison tests
├── templates/                    # Django templates (admin extensions, reports)
├── static/                       # CSS/JS for report views
└── test_screenshots/             # Output directory
    ├── baselines/                # Figma-sourced reference PNGs
    ├── actuals/                  # Live site screenshots
    └── diffs/                    # Highlighted difference images
```

---

## Implementation Phases

### Phase 1: Project Scaffold & Dependencies
- `django-admin startproject qa_figma .`
- Create `figma_integration` and `visual_tests` apps
- Install dependencies: `django`, `pytest`, `pytest-django`, `pytest-playwright`, `playwright`, `pixelmatch`, `Pillow`, `httpx`, `mcp[cli]`, `django-environ`
- Run `playwright install chromium`
- Configure `.env` with `FIGMA_ACCESS_TOKEN` and `FIGMA_FILE_KEY`
- Add Figma + screenshot path settings to `settings.py`

### Phase 2: Figma Client (REST API Wrapper)
- Implement `figma_client.py` with:
  - `get_file(file_key)` — fetch full file JSON (nodes, layers, properties)
  - `get_node(file_key, node_id)` — fetch specific node metadata (width, height, position)
  - `export_image(file_key, node_id, format='png', scale=2)` — export frame as PNG
  - `get_variables(file_key)` — fetch design tokens (colors, spacing, typography)
- Cache exported images to `test_screenshots/baselines/`
- Management command `sync_figma` to pull all frames from a Figma file and store as baseline images

### Phase 3: Playwright Screenshot Capture
- Implement `browser.py` with:
  - `capture_screenshot(url, viewport_width, viewport_height)` — navigate and screenshot
  - Viewport auto-matching: read Figma node dimensions and set Playwright viewport to match
  - Support for full-page and element-scoped screenshots (CSS selector targeting)
- Store screenshots to `test_screenshots/actuals/`

### Phase 4: Visual Comparison Engine
- Implement `comparators.py` with:
  - `compare_images(baseline_path, actual_path, threshold=0.1)` — pixelmatch diff
  - `calculate_fidelity_score(mismatch_count, total_pixels)` — returns 0-100% score
  - `generate_diff_image(baseline, actual, output_path)` — highlighted diff PNG
  - Configurable threshold (sensitivity) and ignore regions (cookie banners, dynamic content)
- Handle dimension mismatch: resize/crop images to match before comparison

### Phase 5: Django Models & Admin
- `DesignRef` model: stores Figma file key, node ID, frame name, page URL mapping, baseline image path
- `TestRun` model: stores run timestamp, status (pass/fail), fidelity score, diff image path
- `DiffResult` model: per-comparison results (baseline, actual, diff paths, mismatch count, score)
- Django admin views to browse test results, view diff images inline, filter by pass/fail
- Custom admin dashboard showing fidelity score trends

### Phase 6: pytest Test Suite
- `conftest.py` fixtures:
  - `figma_baseline` — fetches and caches Figma baseline for a given frame name
  - `browser_page` — Playwright page with viewport matched to Figma dimensions
  - `visual_diff` — pixelmatch comparison helper
- `test_visual_diff.py` — parametrized tests mapping each Figma frame to live URL
- Assertion: `assert fidelity_score > 95.0` (configurable threshold per test)
- Auto-save diff images on failure for review

### Phase 7: MCP Server (LLM-Driven Testing)
- Build `mcp_server.py` using FastMCP SDK exposing tools:
  - `compare_design_to_live(figma_node_id, url)` — full comparison pipeline, returns score + diff
  - `list_figma_designs(file_key)` — list all frames/pages in a Figma file
  - `get_design_metadata(file_key, node_id)` — return design specs (colors, spacing, typography)
  - `run_test_suite(suite_id)` — execute a predefined set of comparisons
  - `get_fidelity_report(run_id)` — return detailed report with diff image references
- MCP resources for design context (variables, component structure)
- This allows an LLM (Claude, etc.) to autonomously run visual tests, diagnose failures, and suggest fixes

### Phase 8: HTML Report & Dashboard
- Django view rendering an HTML report per test run:
  - Side-by-side: Figma baseline | Live screenshot | Diff overlay
  - Fidelity score badge (green/amber/red)
  - Per-component breakdown (if using selector-scoped comparisons)
  - Historical trend chart (fidelity score over time)
- Optional: JSON API endpoint for CI integration

---

## Key Design Decisions

### Figma MCP vs REST API
- **Primary**: Use Figma REST API (`httpx` calls) for the core pipeline — more reliable for automated/CI use, no paid plan requirement, full control
- **Secondary**: Build a custom MCP server that wraps these capabilities as tools — enables LLM-driven exploratory testing and diagnosis
- **Optional**: Connect to the official Figma MCP server (`https://mcp.figma.com/mcp`) if you have a paid Figma Dev seat — gives you `get_screenshot`, `get_variable_defs`, `get_design_context` directly

### Dimension Alignment (Critical Challenge)
- Figma exports frames at their intrinsic pixel size
- Playwright must set viewport to match Figma frame dimensions exactly
- Use `get_metadata` or REST API node data to read width/height before screenshotting
- pixelmatch requires identical image dimensions — resize if needed

### Threshold Tuning
- Start with `threshold=0.1` (pixelmatch default — perceptual, accounts for anti-aliasing)
- Set fidelity pass threshold at 95% initially, tune per project
- Support ignore regions for dynamic content (timestamps, user data, ads)

---

## Dependencies (requirements.txt)

```
django>=5.0
pytest>=8.0
pytest-django>=4.8
pytest-playwright>=0.5
playwright>=1.48
pixelmatch>=0.4
Pillow>=10.0
httpx>=0.27
mcp[cli]>=1.27
django-environ>=0.11
```

---

## Open Questions (Need From You)

1. **Figma file key** — the file you want to test against (from the Figma URL: `figma.com/design/<FILE_KEY>/...`)
2. **Figma access token** — personal access token from Figma settings (or do you have a paid Dev seat for the official MCP server?)
3. **Target website URL** — the live/local site to compare against (e.g., `http://localhost:8000`)
4. **Which frames to test** — specific page names/frames in Figma, or should the system auto-discover all top-level frames?
5. **Fidelity threshold** — what % match is acceptable? (default: 95%)
6. **Do you want the MCP server?** — Phase 7 is optional. It adds LLM-driven testing but is not required for the core pipeline.

---

## Estimated Effort

| Phase | Complexity | Can Parallelize? |
|---|---|---|
| 1. Scaffold | Low | No (foundation) |
| 2. Figma Client | Medium | Yes (after Phase 1) |
| 3. Playwright Capture | Medium | Yes (after Phase 1) |
| 4. Comparison Engine | Medium | Yes (after Phase 1) |
| 5. Models & Admin | Low | Yes (after Phase 1) |
| 6. pytest Suite | Medium | After Phases 2-4 |
| 7. MCP Server | High | After Phases 2-4 |
| 8. HTML Report | Medium | After Phase 5 |

Phases 2, 3, 4, and 5 can all be built in parallel once the scaffold is ready.