# SpriteFlow

> 基于节点的 2D 游戏资产生产管线平台 — 组合、生成、处理、导出。

---

## 概述

SpriteFlow 是一个 **DAG 节点流水线平台**，将 AI 图片生成、视频生成、图片后处理编排为自动化资产生产管线。面向需要批量生产精灵图、角色变体、精灵表、特效的 **2D 游戏开发者**。

### 核心能力

- **AI 生成** — 文生图、图生图、多图融合、序列帧生成
- **角色流水线** — 主模板 → 方向变体 → 动画精灵 → 精灵表
- **图片处理** — 背景移除、精灵对齐、精灵表打包、视频帧提取
- **视频生成** — 通过 Seedance 实现文生视频和图生视频
- **资产管理** — 上传、组织、标签、分组、收藏、血缘追踪
- **可视化图编辑器** — 基于 React Flow 的拖拽式流水线编排
- **批量生产** — 规格 × 角色 × 动作矩阵生成
- **能力路由** — 多供应商路由，支持降级链路和热重载

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
│   ├── engine/               # 执行引擎
│   │   ├── cache.py          # 内容寻址缓存
│   │   ├── context.py        # 执行上下文
│   │   ├── dag.py            # DAG 数据结构 & 校验
│   │   ├── executor.py       # 拓扑排序并行执行器
│   │   ├── node.py           # 节点基类 & 注册表
│   │   ├── sprite_aligner.py # 精灵边界框对齐
│   │   ├── types.py          # 端口类型系统
│   │   └── video_worker.py   # 异步视频任务轮询器
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
│   ├── storage/              # 存储后端
│   │   ├── cos_storage.py    # 腾讯云 COS 对象存储
│   │   └── local_storage.py  # 本地文件系统降级方案
│   ├── templates/            # Prompt 模板系统
│   │   ├── api.py            # 模板 CRUD API
│   │   ├── db.py             # 模板 SQLite 层
│   │   ├── models.py         # 模板数据模型
│   │   └── seed.py           # 预置模板
│   ├── config.py             # 配置（环境变量）
│   └── __main__.py           # CLI 入口（serve）
├── tests/                    # 后端测试 (pytest)
├── web/                      # 前端 (React + TypeScript)
│   └── src/
│       ├── components/       # UI 组件
│       │   ├── graph/        # 流水线图编辑器
│       │   └── layout/       # 应用外壳、侧边栏、顶栏
│       ├── pages/            # 路由页面
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

---

## 支持的 AI 供应商

| 供应商 | 能力 | API 密钥 |
|------|------|----------|
| **Seedream 5.0** | text2img、img2img、multi_fusion、sequential、character_master、four_view | `ARK_API_KEY` |
| **Seedance** | text2video、img2video | `ARK_API_KEY` |
| **OpenRouter** | text2img、img2img、character_master、four_view | `OPENROUTER_API_KEY` |
| **Rembg** | remove_bg（本地运行，无需密钥） | — |
| **Volcengine Image** | enhance、inpaint、outpaint、cut、slim、resize、remove_bg | `VOLC_ACCESS_KEY_ID` |

---

## 测试

```bash
uv run pytest
```

---

## License

MIT
