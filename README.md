# SpriteFlow

> A node-based pipeline platform for 2D game asset production — compose, generate, process, and export.

[中文文档](README_zh-CN.md)

---

## Overview

SpriteFlow is a **DAG-node pipeline platform** that orchestrates AI image generation, video generation, and image post-processing into automated asset production pipelines. It targets **2D game developers** who need to batch-produce sprites, character variants, sprite sheets, and VFX at scale.

### Key Capabilities

- **AI Generation** — Text-to-Image, Image-to-Image, Multi-Image Fusion, Sequential Frame Generation
- **AI Workflow** — Visual node editor with presets, real-time execution, resume-from-failed, text/image/video/audio nodes
- **Model Manager** — Multi-provider model registry with channels, routing, and cost tracking
- **Character Pipeline** — Master template → direction variants → animation sprites → sprite sheets
- **Image Processing** — Background removal, sprite alignment, sprite sheet packing, video frame extraction with key frame selection (cycle detection / uniform / diversity), image grid merge
- **Video Generation** — Text-to-Video and Image-to-Video via Seedance
- **Asset Management** — Upload, organize, tag, group, favorite, lineage tracking
- **Visual Graph Editor** — Drag-and-drop pipeline composition with React Flow
- **Interactive AI Inpainting** — Mask drawing + AI-powered inpainting/erasing via Jimeng
- **Pixel Editor** — Pixel-level brush, eraser, eyedropper, and selection tools for sprite refinement
- **Custom Components** — Extensible plugin framework for custom AI nodes with credential management, testing, and validation
- **Batch Production** — Spec × Character × Action matrix generation
- **Capability Routing** — Multi-provider routing with fallback chains and hot reload

---

## Tech Stack

### Backend (Python)

| Category | Technology | Purpose |
|----------|------------|---------|
| **Web Framework** | FastAPI + Uvicorn | REST API + SSE streaming |
| **Data Validation** | Pydantic + pydantic-settings | Request model validation & env config |
| **Async Database** | aiosqlite | Assets/tasks/templates/config persistence |
| **AI Clients** | openai + replicate + ollama | Multi-provider model client SDKs |
| **ORM** | SQLAlchemy (asyncio) | Workflow/model manager persistence |
| **Image Processing** | Pillow + NumPy | Format conversion, sprite alignment, spritesheet packing |
| **Video Processing** | OpenCV | Frame extraction & cropping |
| **AI Background Removal** | rembg | Local AI matting (offline) |
| **Config Management** | PyYAML + python-dotenv | YAML routing config & .env vars |
| **HTTP Client** | httpx + urllib | Provider API calls (sync/async) |
| **Cloud Storage** | cos-python-sdk-v5 | Tencent COS object storage |
| **SSE** | sse-starlette | Graph execution progress streaming |
| **File Upload** | python-multipart | FormData file upload |
| **Async I/O** | aiofiles | Async file reads/writes |
| **Package Management** | uv + hatchling | Dependency management & build |
| **Testing** | pytest + pytest-asyncio + respx | Unit tests & HTTP mocking |

### Frontend (React + TypeScript)

| Category | Technology | Purpose |
|----------|------------|---------|
| **Framework** | React 18 + TypeScript 5 | UI framework & type safety |
| **Build Tool** | Vite 5 | Dev server & production build |
| **CSS** | Tailwind CSS 3 + PostCSS + Autoprefixer | Utility-first styling |
| **Flow Editor** | @xyflow/react (React Flow) | Drag-and-drop DAG pipeline editing |
| **Image Editor** | react-filerobot-image-editor | Crop/rotate/color/filter/watermark |
| **Pixel Editor** | Canvas API (custom) | Pixel-level brush/eraser/selection |
| **Canvas Interaction** | react-konva + konva | Frame annotation & spritesheet preview |
| **Browser Matting** | @imgly/background-removal | Client-side AI matting (WASM) |
| **State Management** | Zustand 5 | Theme switching & sidebar menu |
| **Data Fetching** | @tanstack/react-query 5 | Server state cache & optimistic updates |
| **Routing** | react-router-dom 6 | SPA routing |
| **i18n** | i18next + react-i18next | Chinese/English switching |
| **GIF Processing** | gifenc + gifuct-js | GIF encoding/decoding & frame extraction |
| **File Handling** | JSZip | Batch frame download packaging |

### AI Providers

| Provider | Model/Capability | Purpose |
|----------|------------------|---------|
| **Seedream 5.0** (Volcano ARK) | doubao-seedream-5.0 | Text2img, img2img, multi-fusion, sequential, character generation |
| **Seedance** (Volcano ARK) | doubao-seedance-1.0 | Text2video, img2video |
| **OpenRouter** | Multi-model gateway | LLM prompt optimization & image generation |
| **Jimeng Inpainting** (Volcano Vision) | jimeng_image2image_dream_inpaint | Interactive AI inpainting |
| **Rembg** | isnet series | Local AI background removal |
| **Volcengine Image** (Volcano Vision) | Image enhancement/repair | Watermark removal, quality enhancement, matting |
| **Jimeng Inpainting** (Volcano Vision) | interactive inpaint, erase | `VOLC_ACCESS_KEY_ID` |
| **Seedance Pro Fast** (Custom Component) | text2video, img2video (advanced params) | `ARK_API_KEY` |
| **imgly Background Removal** (Frontend) | isnet quantized model | Browser-side WASM AI matting |

### Storage & Infrastructure

| Category | Technology | Notes |
|----------|------------|-------|
| **Database** | SQLite (aiosqlite) | Embedded, zero-config, Chinese FTS |
| **Cloud Storage** | Tencent COS | Production image storage (falls back to local FS) |
| **Cache** | Content-addressable (SHA256) | Node output dedup, avoids redundant AI API calls |
| **Auth Signing** | HMAC-SHA256 (Volcengine V4) | Volcano Vision service API signing |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   Web Frontend (React)                    │
│    @xyflow/react · Konva · Tailwind · Zustand · RQ      │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────▼─────────────────────────────────┐
│                    FastAPI Backend                        │
│     /api/nodes · /api/graphs · /api/generate             │
│     /api/assets · /api/videos · /api/routing             │
│     /api/menu · /api/config · /api/components            │
│     /api/image-editor · /api/workflow · /api/model-manager│
└────────────────────────┬─────────────────────────────────┘
                         │
      ┌──────────────────┼─────────────────────┐
      ▼                  ▼                     ▼
┌──────────┐   ┌──────────────┐   ┌────────────────┐
│ Executor │   │ VideoWorker  │   │ IngestPipeline │
│   DAG    │   │(poll Seedance)│   │  (COS+SQLite)  │
└────┬─────┘   └──────────────┘   └────────────────┘
     │
┌────▼─────────────────────────────────────────────────────┐
│                    CapabilityRouter                       │
│       routing.yaml + SQLite config persistent            │
└────┬─────────────────────────────────────────────────────┘
     │
┌────▼─────────────────────────────────────────────────────┐
│         Providers + ComponentRegistry                     │
│   Seedream · Seedance · OpenRouter · Rembg · Volcengine  │
│   Custom Components (Seedance Pro Fast, ...)              │
└──────────────────────────────────────────────────────────┘
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
├── runs/                     # Runtime output (video frames, matte results)
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
│   ├── graph/               # Pipeline graph validation & DAG build
│   │   ├── bridge.py         # Graph → DAG conversion & cycle detection
│   │   ├── models.py         # Graph data models
│   │   └── store.py          # Graph persistence (SQLite/JSON)
│   ├── engine/               # Execution engine
│   │   ├── cache.py          # Content-addressable cache
│   │   ├── context.py        # Execution context
│   │   ├── dag.py            # DAG data structure & validation
│   │   ├── executor.py       # Topological parallel executor
│   │   ├── node.py           # Node base class & registry
│   │   ├── sprite_aligner.py # Sprite bounding-box aligner
│   │   ├── types.py          # Port type system
│   │   └── video_worker.py   # Async video task poller
│   ├── model_manager/        # Multi-provider model management
│   │   ├── database.py       # SQLite layer (models, channels, routes)
│   │   ├── models.py         # Data models (ModelConfig, Channel, Route)
│   │   ├── schemas.py        # Pydantic schemas
│   │   ├── providers/        # Provider integrations
│   │   │   ├── base.py       # Abstract provider interface
│   │   │   ├── openai.py     # OpenAI-compatible API provider
│   │   │   ├── ollama.py     # Ollama local model provider
│   │   │   ├── openrouter.py # OpenRouter multi-model gateway
│   │   │   └── replicate.py  # Replicate.com model provider
│   │   ├── routers/          # FastAPI routers
│   │   │   ├── channel_router.py  # Channel CRUD endpoints
│   │   │   └── route_router.py    # Route management endpoints
│   │   └── services/         # Business logic
│   │       ├── channel_service.py # Channel lifecycle management
│   │       └── route_service.py   # Model routing service
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
│   ├── tools/               # Utility tools
│   │   └── watermark_remover.py  # AI video watermark removal (Canny + TELEA)
│   ├── storage/              # Storage backends
│   │   ├── cos_storage.py    # Tencent COS cloud storage
│   │   └── local_storage.py  # Local filesystem fallback
│   ├── components/           # Custom component framework
│   │   ├── base.py           # Component base class & metadata
│   │   ├── registry.py       # Global component registry
│   │   ├── router.py         # Component management & test API
│   │   ├── schema_bridge.py  # Component ↔ node-schema converter
│   │   └── ai/               # AI components
│   │       └── seedance_pro_fast.py  # Seedance 1.0 Pro Fast
│   ├── templates/            # Prompt template system
│   │   ├── api.py            # Template CRUD API
│   │   ├── db.py             # Template SQLite layer
│   │   ├── models.py         # Template data models
│   │   └── seed.py           # Preset templates
│   ├── workflow/             # AI workflow engine
│   │   ├── models.py         # Workflow + Preset data models
│   │   ├── database.py       # SQLite layer (workflows, presets, runs)
│   │   ├── workflow_helper.py # Workflow CRUD + preset seeding
│   │   ├── routers/          # FastAPI routers
│   │   │   ├── app_router.py       # App-level workflow settings
│   │   │   ├── workflow_router.py  # Workflow CRUD + preset endpoints
│   │   │   ├── cost_router.py      # Cost estimation endpoint
│   │   │   └── model_router.py     # Model listing endpoint
│   │   └── services/         # Business logic
│   │       ├── base.py             # Provider service interface
│   │       ├── model_registry.py   # Model schema registry
│   │       ├── ollama_service.py   # Ollama model service
│   │       ├── openai_service.py   # OpenAI model service
│   │       └── replicate_service.py # Replicate model service
│   ├── config.py             # Settings (env vars)
│   └── __main__.py           # CLI entry (serve)
├── tests/                    # Backend tests (pytest)
├── web/                      # Frontend (React + TypeScript)
│   └── src/
│       ├── components/       # UI components
│       │   ├── graph/        # Pipeline graph editor
│       │   ├── layout/       # App shell, sidebar, topbar
│       │   ├── InteractiveEditor/  # Interactive image editor
│       │   └── PixelEditor/  # Pixel-level sprite editor
│       ├── pages/            # Route pages
│       │   ├── Assets/       # Asset library
│       │   ├── Editor/       # Interactive editor
│       │   ├── Generate/     # Quick generation
│       │   ├── GraphEditor/  # Graph pipeline editor
│       │   ├── GraphList/    # Graph list
│       │   ├── Routing/      # Capability routing
│       │   ├── SpriteSheet/  # Sprite sheet tools
│       │   ├── Templates/    # Prompt templates
│       │   ├── Video/        # Video generation
│       │   ├── VideoFrames/  # Video frame extraction
│       │   ├── model-manager/  # Model manager (channels + routes)
│       │   ├── components/     # Custom component management
│       │   └── workflow/     # AI workflow editor + list
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
| **ExtractFrames** | Process | Extract frames from video with key frame selection (cycle detection / uniform / diversity) |
| **PackSpritesheet** | Process | Pack frames into sprite sheet |
| **GridMerge** | Process | Merge multiple images into a configurable grid (columns × rows) |
| **SaveAsset** | Output | Save images to library |

### Pipeline Nodes

| Node | Description |
|------|-------------|
| **CharacterMaster** | Generate character base from template |
| **DirectionVariant** | Generate direction variants (up/down/left/right) |
| **AnimationSprite** | Generate animation frames from action template |


### Custom Components (Extensible)

| Component | Description |
|-----------|-------------|
| **SeedanceProFast** | Seedance 1.0 Pro Fast video generation with custom parameter presets, credential management, and test/validate API |
| **VideoFrameExtract** | Extract frames from video with key frame selection (cycle detection, uniform, diversity sampling) |
| **ImageGridMerge** | Merge multiple images into a grid layout with configurable columns, rows, and spacing |

Custom components are self-contained plugins with independent schemas, credentials, and execution logic. They integrate into the workflow engine via [ComponentRegistry](src/spriteflow/components/registry.py) and can be managed through the [ComponentsPage](web/src/pages/components/ComponentsPage.tsx) UI. Single-node execution automatically resolves upstream outputs via handle-to-parameter edge injection.

---

## Supported AI Providers

| Provider | Capabilities | API Key |
|----------|-------------|---------|
| **Seedream 5.0** | text2img, img2img, multi_fusion, sequential, character_master, four_view | `ARK_API_KEY` |
| **Seedance** | text2video, img2video | `ARK_API_KEY` |
| **OpenRouter** | text2img, img2img, character_master, four_view | `OPENROUTER_API_KEY` |
| **Rembg** | remove_bg (local, no key needed) | — |
| **Volcengine Image** | enhance, inpaint, outpaint, cut, slim, resize, remove_bg | `VOLC_ACCESS_KEY_ID` |
| **Jimeng Inpainting** (Volcano Vision) | interactive inpaint, erase | `VOLC_ACCESS_KEY_ID` |
| **Seedance Pro Fast** (Custom Component) | text2video, img2video (advanced params) | `ARK_API_KEY` |

---

## Testing

```bash
uv run pytest
```

---

## License

MIT
