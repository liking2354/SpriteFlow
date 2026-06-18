# SpriteFlow

> 基于节点的 2D 游戏资产生产管线平台 — 组合、生成、处理、导出。

---

## 概述

SpriteFlow 是一个 **DAG 节点流水线平台**，将 AI 图片生成、视频生成、图片后处理编排为自动化资产生产管线。面向需要批量生产精灵图、角色变体、精灵表、特效的 **2D 游戏开发者**。

### 核心能力

- **AI 生成** — 文生图、图生图、多图融合、序列帧生成
- **AI 工作流** — 可视化节点编辑器，支持预设模板、实时执行、文本/图片/视频/音频节点
- **模型管理** — 多供应商模型注册中心，支持渠道管理、路由配置和费用统计
- **角色流水线** — 主模板 → 方向变体 → 动画精灵 → 精灵表
- **图片处理** — 背景移除、精灵对齐、精灵表打包、视频帧提取
| **AI 客户端** | openai + replicate + ollama | 多供应商模型客户端 SDK |
- **视频生成** — 通过 Seedance 实现文生视频和图生视频
- **资产管理** — 上传、组织、标签、分组、收藏、血缘追踪
- **可视化图编辑器** — 基于 React Flow 的拖拽式流水线编排
- **交互式 AI 修复** — 蒙版绘制 + AI 智能修复/擦除（基于即梦 Jimeng）
- **像素编辑器** — 像素级画笔、橡皮、吸管、框选移动工具，用于精灵图精细处理
- **自定义组件** — 可扩展插件框架，支持自定义 AI 节点、凭据管理、测试和校验
- **批量生产** — 规格 × 角色 × 动作矩阵生成
- **能力路由** — 多供应商路由，支持降级链路和热重载

---

## 技术栈

### 后端 (Python)

| 类别 | 技术 | 用途 |
|------|------|------|
| **Web 框架** | FastAPI + Uvicorn | REST API 服务 + SSE 流式推送 |
| **数据验证** | Pydantic + pydantic-settings | 请求模型校验 & 环境变量配置管理 |
| **异步数据库** | aiosqlite | 资产/任务/模板/配置持久化存储 |
| **ORM** | SQLAlchemy (asyncio) | 工作流/模型管理器持久化 |
| **图像处理** | Pillow + NumPy | 图片格式转换、精灵对齐、精灵表打包 |
| **视频处理** | OpenCV | 视频帧提取与裁剪 |
| **AI 背景移除** | rembg | 本地 AI 抠图（无需网络） |
| **配置管理** | PyYAML + python-dotenv | YAML 路由配置 & .env 环境变量 |
| **HTTP 客户端** | httpx + urllib | 供应商 API 调用（同步/异步） |
| **云存储** | cos-python-sdk-v5 | 腾讯云 COS 对象存储 |
| **SSE 推送** | sse-starlette | 管线图执行进度实时推送 |
| **文件上传** | python-multipart | FormData 文件上传 |
| **异步 I/O** | aiofiles | 异步文件读写 |
| **包管理** | uv + hatchling | 依赖管理 & 构建打包 |
| **测试** | pytest + pytest-asyncio + respx | 单元测试 & HTTP Mock |

### 前端 (React + TypeScript)

| 类别 | 技术 | 用途 |
|------|------|------|
| **框架** | React 18 + TypeScript 5 | UI 框架 & 类型安全 |
| **构建工具** | Vite 5 | 开发服务器 & 生产构建 |
| **CSS** | Tailwind CSS 3 + PostCSS + Autoprefixer | 原子化样式 |
| **流程图编辑器** | @xyflow/react (React Flow) | 拖拽式 DAG 管线图编辑 |
| **图片编辑器** | react-filerobot-image-editor | 裁剪/旋转/调色/滤镜/水印/标注 |
| **像素编辑器** | Canvas API (自研) | 像素级画笔/橡皮/框选移动 |
| **Canvas 交互** | react-konva + konva | 序列帧标注 & 精灵表预览 |
| **浏览器抠图** | @imgly/background-removal | 客户端 AI 抠图（WASM 本地推理） |
| **状态管理** | Zustand 5 | 主题切换 & 侧边栏菜单偏好 |
| **数据请求** | @tanstack/react-query 5 | 服务端状态缓存 & 乐观更新 |
| **路由** | react-router-dom 6 | 单页应用路由 |
| **国际化** | i18next + react-i18next | 中/英文切换 |
| **GIF 处理** | gifenc + gifuct-js | GIF 编解码 & 帧提取 |
| **文件处理** | JSZip | 批量帧下载打包 |

### AI 供应商

| 供应商 | 模型/能力 | 用途 |
|------|-----------|------|
| **Seedream 5.0** (火山 ARK) | doubao-seedream-5.0 | 文生图、图生图、多图融合、序列帧、角色生成 |
| **Seedance** (火山 ARK) | doubao-seedance-1.0 | 文生视频、图生视频 |
| **OpenRouter** | 多模型网关 | LLM 驱动的提示词优化 & 图像生成 |
| **即梦AI Inpainting** (火山视觉) | jimeng_image2image_dream_inpaint | 交互式 AI 局部重绘 |
| **Rembg** | isnet 系列 | 本地 AI 背景移除 |
| **Volcengine Image** (火山视觉) | 图像增强/修复 | 去水印、画质增强、抠图 |
| **imgly Background Removal** (前端) | isnet 量化模型 | 浏览器端 WASM AI 抠图 |

### 存储 & 基础设施

| 类别 | 技术 | 说明 |
|------|------|------|
| **数据库** | SQLite (aiosqlite) | 嵌入式中文搜索，零配置 |
| **云存储** | 腾讯云 COS | 生产环境图片存储（降级为本地文件系统） |
| **缓存** | 内容寻址存储 (SHA256) | 节点输出去重，避免重复调用 AI API |
| **签名认证** | HMAC-SHA256 (Volcengine V4) | 火山引擎视觉服务 API 签名 |

---

## 架构

```
┌──────────────────────────────────────────────────────┐
│                  Web 前端 (React)                     │
│   @xyflow/react · Konva · Tailwind · Zustand · RQ   │
└──────────────────────┬───────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼───────────────────────────────┐
│                  FastAPI 后端                          │
│      /api/nodes · /api/graphs                       │
│      /api/generate · /api/assets · /api/videos        │
│      /api/routing · /api/menu · /api/config           │
└──────────────────────┬───────────────────────────────┘
                       │
    ┌──────────────────┼──────────────────┐
    ▼                  ▼                  ▼
┌────────┐    ┌─────────────┐    ┌──────────────┐
│Executor│    │ VideoWorker  │    │IngestPipeline│
│  DAG   │    │(轮询 Seedance)│   │  (COS+SQLite) │
└───┬────┘    └─────────────┘    └──────────────┘
    │
┌───▼──────────────────────────────────────────────────┐
│                 CapabilityRouter                      │
│     routing.yaml + SQLite 配置持久化                   │
└───┬──────────────────────────────────────────────────┘
    │
┌───▼──────────────────────────────────────────────────┐
│                     供应商                             │
│  Seedream · Seedance · OpenRouter · Rembg · Volcengine│
└──────────────────────────────────────────────────────┘
```

---

## 快速开始

### 环境要求

- Python ≥ 3.12
- [uv](https://github.com/astral-sh/uv)（Python 包管理器）
- Node.js ≥ 18（用于前端）

### 1. 克隆并安装

```bash
git clone <repo-url>
cd SpriteFlow

# 后端
uv sync

# 前端
cd web
npm install
cd ..
```

### 2. 配置

复制 `.env.example` 为 `.env` 并填入 API 密钥：

```bash
cp .env.example .env
```

| 环境变量 | 是否必需 | 用途 |
|----------|----------|------|
| `ARK_API_KEY` | 是 | 火山引擎 ARK（Seedream + Seedance） |
| `OPENROUTER_API_KEY` | 可选 | OpenRouter 多模型网关 |
| `COS_SECRET_ID` / `COS_SECRET_KEY` | 可选 | 腾讯云 COS 对象存储（未配置则本地存储） |
| `VOLC_ACCESS_KEY_ID` / `VOLC_SECRET_ACCESS_KEY` | 可选 | 火山引擎 AI 图像处理 |

### 3. 运行

**启动 API 服务 + 前端开发服务器：**

```bash
# 终端 1：后端
uv run python -m spriteflow serve --port 8000

# 终端 2：前端
cd web && npm run dev
```

然后打开 **http://localhost:5173**。

---

## 项目结构

```
SpriteFlow/
├── config/
│   └── routing.yaml          # 能力 → 供应商路由配置
├── data/                     # 运行时数据（数据库、存储、缓存）
├── docs/                     # 设计文档
├── graphs/                   # 流水线图定义 (JSON)
│   └── presets/              # 预设图模板
├── runs/                     # 运行时输出（视频抽帧、抠图结果等）
├── scripts/                  # 工具脚本
├── src/spriteflow/           # 后端 (Python)
│   ├── api/                  # FastAPI 路由
│   │   ├── app.py            # 应用工厂 & 生命周期
│   │   ├── assets.py         # 资产 CRUD + AI 处理
│   │   ├── config.py         # 供应商配置
│   │   ├── generate.py       # 快速生成 + 批量
│   │   ├── graphs.py         # 流水线图 CRUD + 执行
│   │   ├── jobs.py           # 生成任务记录
│   │   ├── menu.py           # 侧边栏菜单持久化
│   │   ├── nodes.py          # 节点模式列表
│   │   ├── routing.py        # 能力路由配置
│   │   ├── videos.py         # 视频生成任务
│   │   ├── video_frames.py    # 视频帧提取
│   ├── asset_hub/            # 资产存储与管理
│   │   ├── db.py             # SQLite CRUD（资产、任务、配置）
│   │   ├── ingest.py         # 上传 + 入库流水线
│   │   └── models.py         # 数据模型 + SQL 建表
│   ├── graph/               # 管线图校验和 DAG 构建
│   │   ├── bridge.py         # 图 → DAG 转换 + 环检测
│   │   ├── models.py         # 图数据模型
│   │   └── store.py          # 图持久化 (SQLite/JSON)
│   ├── engine/               # 执行引擎
│   │   ├── cache.py          # 内容寻址缓存
│   │   ├── context.py        # 执行上下文
│   │   ├── dag.py            # DAG 数据结构 & 校验
│   │   ├── executor.py       # 拓扑排序并行执行器
│   │   ├── node.py           # 节点基类 & 注册表
│   │   ├── sprite_aligner.py # 精灵边界框对齐
│   │   ├── types.py          # 端口类型系统
│   │   └── video_worker.py   # 异步视频任务轮询器
│   ├── model_manager/        # 多供应商模型管理
│   │   ├── database.py       # SQLite 层（模型、渠道、路由）
│   │   ├── models.py         # 数据模型（ModelConfig、Channel、Route）
│   │   ├── schemas.py        # Pydantic 模式定义
│   │   ├── providers/        # 供应商集成
│   │   │   ├── base.py       # 抽象供应商接口
│   │   │   ├── openai.py     # OpenAI 兼容 API 供应商
│   │   │   ├── ollama.py     # Ollama 本地模型供应商
│   │   │   ├── openrouter.py # OpenRouter 多模型网关
│   │   │   └── replicate.py  # Replicate.com 模型供应商
│   │   ├── routers/          # FastAPI 路由
│   │   │   ├── channel_router.py  # 渠道 CRUD 端点
│   │   │   └── route_router.py    # 路由管理端点
│   │   └── services/         # 业务逻辑
│   │       ├── channel_service.py # 渠道生命周期管理
│   │       └── route_service.py   # 模型路由服务
│   ├── nodes/                # 内置节点
│   │   ├── load_asset.py     # 从资产库加载图片
│   │   ├── text2img.py       # 文生图
│   │   ├── img2img.py        # 图生图
│   │   ├── multi_image_fusion.py  # 多参考图融合
│   │   ├── sequential_images.py   # 序列帧生成
│   │   ├── remove_bg.py      # 背景移除
│   │   ├── sprite_align.py   # 精灵对齐
│   │   ├── extract_frames.py # 视频帧提取
│   │   ├── pack_spritesheet.py    # 精灵表打包
│   │   ├── save_asset.py     # 保存到资产库
│   │   ├── character_master.py    # 角色主模板生成
│   │   ├── direction_variant.py   # 方向变体节点
│   │   └── animation_sprite.py    # 动画精灵节点
│   ├── providers/            # AI 能力供应商
│   │   ├── router.py         # CapabilityRouter（路由 + 降级）
│   │   ├── seedream.py       # 火山 ARK Seedream 5.0
│   │   ├── seedance.py       # 火山 ARK Seedance
│   │   ├── openrouter.py     # OpenRouter 多模型
│   │   ├── rembg_provider.py # 本地背景移除
│   │   └── volcengine_image.py # 火山引擎 AI 图像处理
│   ├── tools/               # 实用工具
│   │   └── watermark_remover.py  # AI 视频水印去除 (Canny + TELEA)
│   ├── storage/              # 存储后端
│   │   ├── cos_storage.py    # 腾讯云 COS 对象存储
│   │   └── local_storage.py  # 本地文件系统降级方案
│   ├── components/           # 自定义组件框架
│   │   ├── base.py           # 组件基类和元数据
│   │   ├── registry.py       # 全局组件注册表
│   │   ├── router.py         # 组件管理和测试 API
│   │   ├── schema_bridge.py  # 组件 ↔ node-schema 转换
│   │   └── ai/               # AI 组件
│   │       └── seedance_pro_fast.py  # Seedance 1.0 Pro Fast
│   ├── templates/            # Prompt 模板系统
│   │   ├── api.py            # 模板 CRUD API
│   │   ├── db.py             # 模板 SQLite 层
│   │   ├── models.py         # 模板数据模型
│   │   └── seed.py           # 预置模板
│   ├── workflow/             # AI 工作流引擎
│   │   ├── models.py         # 工作流 + 预设数据模型
│   │   ├── database.py       # SQLite 层（工作流、预设、运行记录）
│   │   ├── workflow_helper.py # 工作流 CRUD + 预设种子数据
│   │   ├── routers/          # FastAPI 路由
│   │   │   ├── app_router.py       # 应用级工作流设置
│   │   │   ├── workflow_router.py  # 工作流 CRUD + 预设端点
│   │   │   ├── cost_router.py      # 费用估算端点
│   │   │   └── model_router.py     # 模型列表端点
│   │   └── services/         # 业务逻辑
│   │       ├── base.py             # 供应商服务接口
│   │       ├── model_registry.py   # 模型模式注册表
│   │       ├── model_settings_service.py # 模型默认设置管理
│   │       ├── ollama_service.py   # Ollama 模型服务
│   │       ├── openai_service.py   # OpenAI 模型服务
│   │       └── replicate_service.py # Replicate 模型服务
│   ├── config.py             # 配置（环境变量）
│   └── __main__.py           # CLI 入口（serve）
├── tests/                    # 后端测试 (pytest)
├── web/                      # 前端 (React + TypeScript)
│   └── src/
│       ├── components/       # UI 组件
│       │   ├── graph/        # 流水线图编辑器
│       │   ├── layout/       # 应用外壳、侧边栏、顶栏
│       │   ├── InteractiveEditor/  # 交互式图片编辑器
│       │   └── PixelEditor/  # 像素级精灵编辑器
│       ├── pages/            # 路由页面
│       │   ├── Assets/       # 资产库
│       │   ├── Editor/       # 交互式编辑器
│       │   ├── Generate/     # 快速生成
│       │   ├── GraphEditor/  # 图流水线编辑器
│       │   ├── GraphList/    # 图列表
│       │   ├── Routing/      # 能力路由
│       │   ├── SpriteSheet/  # 精灵表工具
│       │   ├── Templates/    # 提示词模板
│       │   ├── Video/        # 视频生成
│       │   ├── VideoFrames/  # 视频帧提取
│       │   ├── model-manager/  # 模型管理（渠道 + 路由）
│       │   └── workflow/     # AI 工作流编辑器 + 列表
│       ├── stores/           # Zustand 状态（主题、菜单）
│       ├── api/              # API 客户端 & 类型
│       ├── i18n/             # 中英文翻译
│       └── styles/           # 全局 CSS
├── pyproject.toml
└── README.md
```

---

## 可用节点

### 核心节点

| 节点 | 类型 | 说明 |
|------|------|------|
| **LoadAsset** | 输入 | 从资产库加载图片 |
| **Text2Img** | 生成 | 文生图 |
| **Img2Img** | 生成 | 图生图 |
| **MultiImageFusion** | 生成 | 多参考图融合 |
| **SequentialImages** | 生成 | 生成连贯图像序列 |
| **RemoveBG** | 处理 | AI 背景移除 |
| **SpriteAlign** | 处理 | 检测 → 裁剪 → 缩放 → 对齐 |
| **ExtractFrames** | 处理 | 从视频中提取帧 |
| **PackSpritesheet** | 处理 | 将帧打包为精灵表 |
| **SaveAsset** | 输出 | 保存图片到资产库 |

### 流水线节点

| 节点 | 说明 |
|------|------|
| **CharacterMaster** | 从模板生成角色基底 |
| **DirectionVariant** | 生成方向变体（上/下/左/右） |
| **AnimationSprite** | 从动作模板生成动画帧 |


### 自定义组件 (可扩展)

| 组件 | 说明 |
|------|------|
| **SeedanceProFast** | Seedance 1.0 Pro Fast 视频生成，支持自定义参数预设、凭据管理、测试/校验 API |

自定义组件是独立的插件，拥有独立的 schema、凭据和执行逻辑。通过 [ComponentRegistry](src/spriteflow/components/registry.py) 集成到工作流引擎，并通过 [ComponentsPage](web/src/pages/components/ComponentsPage.tsx) 界面管理。

---

## 支持的 AI 供应商

| 供应商 | 能力 | API 密钥 |
|------|------|----------|
| **Seedream 5.0** | text2img、img2img、multi_fusion、sequential、character_master、four_view | `ARK_API_KEY` |
| **Seedance** | text2video、img2video | `ARK_API_KEY` |
| **OpenRouter** | text2img、img2img、character_master、four_view | `OPENROUTER_API_KEY` |
| **Rembg** | remove_bg（本地运行，无需密钥） | — |
| **Volcengine Image** | enhance、inpaint、outpaint、cut、slim、resize、remove_bg | `VOLC_ACCESS_KEY_ID` |
| **即梦AI Inpainting** (火山视觉) | 交互式修复、擦除 | `VOLC_ACCESS_KEY_ID` |
| **Seedance Pro Fast** (自定义组件) | text2video、img2video (高级参数) | `ARK_API_KEY` |

---

## 测试

```bash
uv run pytest
```

---

## License

MIT
