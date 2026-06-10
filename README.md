# SpriteFlow

> A node-based pipeline platform for 2D game asset production — compose, generate, process, and export.

[中文文档](README_zh-CN.md)

---

## Overview

SpriteFlow is a **DAG-node pipeline platform** that orchestrates AI image generation, video generation, and image post-processing into automated asset production pipelines. It targets **2D game developers** who need to batch-produce sprites, character variants, sprite sheets, and VFX at scale.

### Key Capabilities

- **AI Generation** — Text-to-Image, Image-to-Image, Multi-Image Fusion, Sequential Frame Generation
- **Character Pipeline** — Master template → direction variants → animation sprites → sprite sheets
- **Image Processing** — Background removal, sprite alignment, sprite sheet packing, video frame extraction
- **Video Generation** — Text-to-Video and Image-to-Video via Seedance
- **Asset Management** — Upload, organize, tag, group, favorite, lineage tracking
- **Visual Graph Editor** — Drag-and-drop pipeline composition with React Flow
- **Batch Production** — Spec × Character × Action matrix generation
- **Capability Routing** — Multi-provider routing with fallback chains and hot reload

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Web Frontend (React)                 │
│   @xyflow/react · Konva · Tailwind · Zustand · RQ   │
└──────────────────────┬───────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼───────────────────────────────┐
│                  FastAPI Backend                       │
│      /api/nodes · /api/graphs                       │
│      /api/generate · /api/assets · /api/videos        │
│      /api/routing · /api/menu · /api/config           │
└──────────────────────┬───────────────────────────────┘
                       │
    ┌──────────────────┼──────────────────┐
    ▼                  ▼                  ▼
┌────────┐    ┌─────────────┐    ┌──────────────┐
│Executor│    │ VideoWorker  │    │IngestPipeline│
│  DAG   │    │(poll Seedance)│   │  (COS+SQLite) │
└───┬────┘    └─────────────┘    └──────────────┘
    │
┌───▼──────────────────────────────────────────────────┐
│                 CapabilityRouter                      │
│     routing.yaml + SQLite config persistent           │
└───┬──────────────────────────────────────────────────┘
    │
┌───▼──────────────────────────────────────────────────┐
│                     Providers                         │
│  Seedream · Seedance · OpenRouter · Rembg · Volcengine│
└──────────────────────────────────────────────────────┘
```

---

## Getting Started

### Prerequisites

- Python ≥ 3.12
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Node.js ≥ 18 (for frontend)

### 1. Clone & Install

```bash
git clone <repo-url>
cd SpriteFlow

# Backend
uv sync

# Frontend
cd web
npm install
cd ..
```

### 2. Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|----------|----------|---------|
| `ARK_API_KEY` | Yes | Volcano ARK (Seedream + Seedance) |
| `OPENROUTER_API_KEY` | Optional | OpenRouter multi-model gateway |
| `COS_SECRET_ID` / `COS_SECRET_KEY` | Optional | Tencent COS cloud storage (falls back to local) |
| `VOLC_ACCESS_KEY_ID` / `VOLC_SECRET_ACCESS_KEY` | Optional | Volcengine AI image processing |

### 3. Run

**Start API server + frontend dev server:**

```bash
# Terminal 1: Backend
uv run python -m spriteflow serve --port 8000

# Terminal 2: Frontend
cd web && npm run dev
```

Then open **http://localhost:5173**.

---

## Project Structure

```
SpriteFlow/
├── config/
│   └── routing.yaml          # Capability → Provider routing
├── data/                     # Runtime data (DB, storage, cache)
├── docs/                     # Design documents
├── graphs/                   # Pipeline graph definitions (JSON)
│   └── presets/              # Preset graph templates
├── scripts/                  # Utility scripts
├── src/spriteflow/           # Backend (Python)
│   ├── api/                  # FastAPI routes
│   │   ├── app.py            # App factory & lifecycle
│   │   ├── assets.py         # Asset CRUD + AI processing
│   │   ├── config.py         # Provider configuration
│   │   ├── generate.py       # Quick generation + batch
│   │   ├── graphs.py         # Pipeline graph CRUD + execution
│   │   ├── jobs.py           # Generation job records
│   │   ├── menu.py           # Sidebar menu persistence
│   │   ├── nodes.py          # Node schema listing
│   │   ├── routing.py        # Capability routing config
│   │   ├── videos.py         # Video generation tasks
│   │   ├── video_frames.py    # Video frame extraction
│   ├── asset_hub/            # Asset storage & management
│   │   ├── db.py             # SQLite CRUD (assets, jobs, configs)
│   │   ├── ingest.py         # Upload + ingest pipeline
│   │   └── models.py         # Data models + SQL schema
│   ├── engine/               # Execution engine
│   │   ├── cache.py          # Content-addressable cache
│   │   ├── context.py        # Execution context
│   │   ├── dag.py            # DAG data structure & validation
│   │   ├── executor.py       # Topological parallel executor
│   │   ├── node.py           # Node base class & registry
│   │   ├── sprite_aligner.py # Sprite bounding-box aligner
│   │   ├── types.py          # Port type system
│   │   └── video_worker.py   # Async video task poller
│   ├── nodes/                # Built-in nodes
│   │   ├── load_asset.py     # Image input from library
│   │   ├── text2img.py       # Text → Image
│   │   ├── img2img.py        # Image → Image
│   │   ├── multi_image_fusion.py  # Multi-reference fusion
│   │   ├── sequential_images.py   # Sequential frame generation
│   │   ├── remove_bg.py      # Background removal
│   │   ├── sprite_align.py   # Sprite alignment
│   │   ├── extract_frames.py # Video frame extraction
│   │   ├── pack_spritesheet.py    # Sprite sheet packing
│   │   ├── save_asset.py     # Save to library
│   │   ├── character_master.py    # Character master generation
│   │   ├── direction_variant.py   # Direction variant node
│   │   └── animation_sprite.py    # Animation sprite node
│   ├── providers/            # AI capability providers
│   │   ├── router.py         # CapabilityRouter (routing + fallback)
│   │   ├── seedream.py       # Volcano ARK Seedream 5.0
│   │   ├── seedance.py       # Volcano ARK Seedance
│   │   ├── openrouter.py     # OpenRouter multi-model
│   │   ├── rembg_provider.py # Local background removal
│   │   └── volcengine_image.py # Volcengine AI image processing
│   ├── storage/              # Storage backends
│   │   ├── cos_storage.py    # Tencent COS cloud storage
│   │   └── local_storage.py  # Local filesystem fallback
│   ├── templates/            # Prompt template system
│   │   ├── api.py            # Template CRUD API
│   │   ├── db.py             # Template SQLite layer
│   │   ├── models.py         # Template data models
│   │   └── seed.py           # Preset templates
│   ├── config.py             # Settings (env vars)
│   └── __main__.py           # CLI entry (serve)
├── tests/                    # Backend tests (pytest)
├── web/                      # Frontend (React + TypeScript)
│   └── src/
│       ├── components/       # UI components
│       │   ├── graph/        # Pipeline graph editor
│       │   └── layout/       # App shell, sidebar, topbar
│       ├── pages/            # Route pages
│       ├── stores/           # Zustand stores (theme, menu)
│       ├── api/              # API client & types
│       ├── i18n/             # zh-CN / en-US translations
│       └── styles/           # Global CSS
├── pyproject.toml
└── README.md
```

---

## Available Nodes

### Core Nodes

| Node | Type | Description |
|------|------|-------------|
| **LoadAsset** | Input | Load image from asset library |
| **Text2Img** | Generate | Text-to-Image generation |
| **Img2Img** | Generate | Image-to-Image generation |
| **MultiImageFusion** | Generate | Fuse multiple reference images |
| **SequentialImages** | Generate | Generate coherent image sequences |
| **RemoveBG** | Process | AI background removal |
| **SpriteAlign** | Process | Detect → Crop → Scale → Align |
| **ExtractFrames** | Process | Extract frames from video |
| **PackSpritesheet** | Process | Pack frames into sprite sheet |
| **SaveAsset** | Output | Save images to library |

### Pipeline Nodes

| Node | Description |
|------|-------------|
| **CharacterMaster** | Generate character base from template |
| **DirectionVariant** | Generate direction variants (up/down/left/right) |
| **AnimationSprite** | Generate animation frames from action template |

---

## Supported AI Providers

| Provider | Capabilities | API Key |
|----------|-------------|---------|
| **Seedream 5.0** | text2img, img2img, multi_fusion, sequential, character_master, four_view | `ARK_API_KEY` |
| **Seedance** | text2video, img2video | `ARK_API_KEY` |
| **OpenRouter** | text2img, img2img, character_master, four_view | `OPENROUTER_API_KEY` |
| **Rembg** | remove_bg (local, no key needed) | — |
| **Volcengine Image** | enhance, inpaint, outpaint, cut, slim, resize, remove_bg | `VOLC_ACCESS_KEY_ID` |

---

## Testing

```bash
uv run pytest
```

---

## License

MIT
