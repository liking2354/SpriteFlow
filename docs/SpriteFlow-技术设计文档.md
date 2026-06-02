# SpriteFlow 技术设计文档

> 一个面向 2D 游戏素材生产的、节点化可编排的工作流平台
> 输入角色原型 → 编排工作流 → 产出可直接用于游戏引擎的素材（8 方向走/跑/待机/攻击精灵表等）

| | |
|---|---|
| 文档版本 | v0.1（待评审） |
| 目标平台 | macOS（M4 Mac mini 16G 为主力开发/运行机） |
| 目标项目 | yqcr（Godot 4.6 MMORPG） |
| 文档状态 | 草案 — 待用户反馈后迭代 |

---

## 1. 设计目标与范围

### 1.1 我们要解决的核心问题

2D 游戏素材生产的痛点**不在「生成」，而在「编排与后处理」**：

- 一个角色要 8 方向 × N 动作 × M 帧，是一个庞大的笛卡尔积
- 生成只是第一步，真正耗时的是：去背景、帧切分、包围盒对齐、调色板量化、网格拼图、命名规范化
- 不同任务最优的 AI 后端不同（生图 nanobanana 好，生视频 Seedance 好）
- 改一个参数往往要重跑整条链路，既费钱又费时

### 1.2 设计目标

| 目标 | 说明 |
|------|------|
| **组件化** | 每个处理环节是一个独立、可测试、可复用的「节点」 |
| **可编排** | 像 ComfyUI 一样用 DAG 把节点串成工作流，可保存/复用/分享 |
| **后端可切换** | 生图、生视频、去背景各自路由到最优后端（API 或本地） |
| **增量重算** | 改参数时只重跑受影响的节点，命中缓存秒级完成 |
| **产出即用** | 最终导出符合 yqcr 项目命名规范，可直接拖进 Godot |

### 1.3 非目标（明确不做，避免范围蔓延）

- ❌ 不做分布式调度（单机够用，不引入 Airflow/Dagster）
- ❌ 不做实时协作编辑（单人/小团队场景）
- ❌ 第一阶段不做节点画布 UI（先做引擎 + 配置编排，画布最后做）
- ❌ 不自训大模型（复用现成 API / 本地开源模型）

---

## 2. 架构总览

### 2.1 分层架构（限界上下文划分）

```
┌─────────────────────────────────────────────────────────────┐
│ ① 编辑器层 Editor                                              │
│   节点画布拖拽 · 连线 · 参数面板 · 实时预览 · 工作流保存/加载    │
│   技术：React + React Flow（后期）                             │
├─────────────────────────────────────────────────────────────┤
│ ② 引擎内核 Graph Engine（domain 无关，最稳定）                 │
│   DAG 解析 · 拓扑排序 · 类型校验 · 内容寻址缓存 · 调度 · 序列化  │
│   核心契约：Node = (inputs, params) → outputs                 │
├─────────────────────────────────────────────────────────────┤
│ ③ 节点库 Node Library（domain 特定，持续扩展）                 │
│   生成 · 处理 · 像素 · 编排 · 导出 — 每个节点独立可热插拔       │
├──────────────────────────────┬──────────────────────────────┤
│ ④ 能力路由 + 后端适配 Provider │ ⑤ 素材中枢 Asset Hub          │
│   按 capability 路由到 provider│   统一素材模型 · 标签分类       │
│   API / 本地 ComfyUI 可切换    │   血缘 · 去重 · 上传流水线      │
└──────────────────────────────┴──────────────────────────────┘
```

### 2.2 核心架构铁律

> **依赖方向单向向下**：上层依赖下层；③节点库依赖②引擎接口；②引擎内核**绝不**反向依赖③任何具体节点。

这条铁律保证引擎内核保持纯净通用——它能复用到任何 pipeline（音效、UI、关卡生成），而节点库可以随游戏需求无限生长。

### 2.3 技术栈选型

| 层 | 选型 | 理由 |
|----|------|------|
| 引擎 + 节点 | **Python 3.13** | 图像处理生态最强，ComfyUI 同栈可借鉴 |
| 图像处理 | Pillow + numpy + opencv | 调色板量化、最近邻、包围盒全现成 |
| 去背景（本地） | rembg / BiRefNet | M4 可跑，离线 |
| 异步调度 | asyncio | AI 调用是 IO 密集，并发跑 8 方向 |
| 配置/校验 | Pydantic v2 | 工作流 schema、参数类型白送 |
| 持久化 | SQLite | 单机百千张素材级别足够 |
| API 服务 | FastAPI | 与 Pydantic 无缝，给前端/CLI 供接口 |
| 前端（后期） | React + React Flow + TypeScript | 节点画布事实标准 |

---

## 3. 引擎内核设计（②）

### 3.1 节点契约（整个系统的基石）

一个节点 = 声明式元数据（类型 + 参数）+ 一个纯函数 `execute`：

```python
from abc import ABC, abstractmethod

class Node(ABC):
    # ---- 声明式契约：引擎靠这些元数据做校验、连线、缓存 ----
    INPUTS:  dict[str, PortType]    # {"image": IMAGE, "prompt": STRING}
    PARAMS:  dict[str, ParamSpec]   # {"strength": Float(0, 1, default=0.8)}
    OUTPUTS: dict[str, PortType]    # {"image": IMAGE}
    CATEGORY: str = "uncategorized" # 编辑器分类，如 "process/pixel"

    @abstractmethod
    def execute(self, inputs: dict, params: dict, ctx: "Context") -> dict:
        """纯函数：相同输入必产相同输出（缓存的前提）"""
        ...
```

更轻量的写法（推荐，像 FastAPI 装饰器）：

```python
@node(category="process/pixel")
def quantize_palette(image: IMAGE, colors: Int(2, 256) = 32) -> IMAGE:
    """调色板量化：把颜色数限制在 colors 内"""
    return image.quantize(colors=colors, method=Image.MEDIANCUT).convert("RGBA")
```

引擎自动从类型注解抽取端口和参数 schema，写一个新节点只需几行。

### 3.2 端口类型系统

给数据流强类型，连线时校验类型匹配，编辑期就拦掉错误连接：

| 类型 | 含义 |
|------|------|
| `IMAGE` | 单张 RGBA 图（PIL.Image / np.array） |
| `IMAGE_BATCH` | 一组图（8 方向、多帧） |
| `MASK` | 单通道遮罩 |
| `SPRITESHEET` | 拼好的精灵表 + 网格元数据 |
| `PALETTE` | 调色板（颜色列表） |
| `VIDEO` | 视频/帧序列 |
| `STRING` / `INT` / `FLOAT` / `SEED` | 标量参数 |
| `ASSET_REF` | 素材库引用（id） |

### 3.3 三个关键机制

#### 机制 A：内容寻址缓存（content-addressed cache）

```
节点输出 hash = hash(节点类型 + 参数 + 所有上游输入的 hash)
```

落盘到 `.cache/<hash>.png`。改第 8 个节点的参数，前 7 个节点全部命中缓存秒过。
**对 AI 生成尤其关键**：一张图几十秒/几毛钱，缓存让你反复调后处理参数时不再烧钱烧时间。

#### 机制 B：批量是一等公民（batch fanout）

核心需求是 8 方向 × N 动作 × M 帧的笛卡尔积。不能让用户连 152 个节点。

- `Fanout` 节点：输入单图 → 输出 `IMAGE_BATCH`（如 8 方向展开）
- 下游处理节点自动对 batch 里每个元素 `map` 执行
- 失败只重跑该分支，不影响其他方向

#### 机制 C：拓扑排序 + 调度

- 解析 DAG → 检测环 → 拓扑排序得出执行顺序
- IO 密集节点（AI 调用）用 asyncio 并发；CPU 密集节点（图像处理）串行/进程池
- 每个节点带超时保护和重试策略

### 3.4 执行流程示例

```
角色原型(LoadAsset)
   → 8方向展开(Fanout×8)
   → 生成(Provider.generate, 能力=img2img)
   → 去背景(RemoveBG)
   → 帧切分对齐(SplitAlign)
   → 调色板量化(Quantize)
   → 网格拼图(PackGrid)
   → 导出(ExportYqcr)
```

引擎在背后自动完成：拓扑排序、缓存命中、batch 透传、失败重试。

---

## 4. 节点库设计（③）

### 4.1 节点分类

| 类别 | 节点示例 | 说明 |
|------|---------|------|
| **加载类** | LoadAsset, LoadImage | 从素材库/文件取图 |
| **生成类** | Text2Img, Img2Img, Img2Video, ExtractFrames | 声明能力，由路由层决定后端 |
| **处理类** | RemoveBG, SplitFrames, BBoxAlign, Trim, Resize | 后处理脏活累活 |
| **像素类** | QuantizePalette, NearestScale, OutlineDetect | 像素风专用 |
| **编排类** | Fanout8Dir, ActionMatrix, PackGrid | 笛卡尔积展开 + 拼图 |
| **导出类** | ExportYqcr, ExportSpriteFrames, ExportGif | 命名规范 + 引擎格式 |

### 4.2 8 方向编排约定（对接 yqcr）

| dir | 方向 | 素材朝向 |
|-----|------|---------|
| dir1 | SW | 左下 |
| dir2 | W | 左 |
| dir3 | NW | 左上 |
| dir4 | N | 上 |
| dir5 | NE | 右上 |
| dir6 | E | 右 |
| dir7 | SE | 右下 |
| dir8 | S | 下 |

> 顺时针编号。导出命名形如 `knight_walk_dir1_SW_00.png`。

### 4.3 后处理关键节点：BBoxAlign（防抖动）

8 方向各自生成时，角色在画布中的位置会漂移，直接拼图会抖动。BBoxAlign 节点：
1. 检测每帧角色的包围盒（alpha 通道非零区域）
2. 统一对齐到锚点（如脚底中心）
3. 输出位置稳定的帧序列

这是「生成的素材能不能直接用」的分水岭。可直接移植开源项目 `agent-sprite-forge` 的后处理逻辑。

---

## 5. 能力路由与后端适配（④）

### 5.1 核心思想：能力路由，而非 Key 路由

不要「按 API Key 切换」，而要「按能力（capability）路由」。三个独立概念：

| 概念 | 是什么 | 例子 |
|------|--------|------|
| **Capability** | 抽象任务类型 | `text2img`, `img2img`, `img2video`, `remove_bg` |
| **Provider** | 能力的具体实现 | nanobanana, seedance, 即梦, 本地ComfyUI, rembg |
| **Credential** | 访问凭证 | 各家 API Key |

**节点只声明「我需要 text2img 能力」，至于谁干、用哪个 key，交给路由层。**

### 5.2 三层结构

```
节点层    : 声明 need: text2img / img2video / remove_bg
   ↓
路由层    : 读路由表，能力 → provider 映射（支持节点级覆盖 + 回退链）
   ↓
提供商层  : 各 provider 实现统一接口，声明自己的 caps
   ↓
凭证层    : 按 provider 独立存 key，运行时注入
```

### 5.3 统一 Provider 接口

```python
class Provider(ABC):
    name: str
    capabilities: set[Capability]   # {Capability.TEXT2IMG, Capability.IMG2IMG}

    @abstractmethod
    async def invoke(self, cap: Capability, payload: dict, cred: Credential) -> dict:
        ...

class NanoBananaProvider(Provider):
    name = "nanobanana"
    capabilities = {Capability.TEXT2IMG, Capability.IMG2IMG}
    async def invoke(self, cap, payload, cred): ...

class SeedanceProvider(Provider):
    name = "seedance"
    capabilities = {Capability.IMG2VIDEO}
    async def invoke(self, cap, payload, cred): ...

class RembgProvider(Provider):       # 本地，无需 key
    name = "rembg"
    capabilities = {Capability.REMOVE_BG}
    async def invoke(self, cap, payload, cred): ...
```

### 5.4 路由配置（用户可改的一张表）

```yaml
# routing.yaml
routes:
  text2img:   nanobanana
  img2img:    nanobanana
  img2video:  seedance
  remove_bg:  rembg          # 本地，省钱

fallback:                    # 主 provider 失败时的回退链
  img2video: [seedance, jimeng, hunyuan]

credentials:                 # 独立管理，建议走环境变量/keychain
  nanobanana: ${NANO_KEY}
  seedance:   ${ARK_KEY}
```

### 5.5 为什么这样分（开闭原则）

- 换「用哪家」→ 只改路由表一行
- 换 key → 只改凭证
- 加新 provider → 只写一个类，注册即用

三件事互不影响。

---

## 6. 素材中枢（⑤）

### 6.1 核心判断：素材层是数据中枢，不是「文件夹分类」

「上传」和「选择已有」是同一素材库的两种入口：
- **上传** = 新素材走 Ingest 流水线 → 入库
- **选择已有** = 查询素材库（按标签筛）→ 引用

两者最终指向同一张 Asset 表。

### 6.2 素材的三种来源

| 来源 | 例子 | 关键处理 |
|------|------|---------|
| Uploaded | 角色原型、参考图 | 校验、规格化、缩略图、去重 |
| Generated | AI 生成的图/视频 | 关联溯源（哪个工作流+参数） |
| Derived | 去背/切帧/拼图产物 | 关联上游、可重新派生 |

### 6.3 统一素材模型

```python
class Asset:
    id: str
    type: Literal["image", "video", "spritesheet"]
    source: Literal["uploaded", "generated", "derived"]
    uri: str                # 文件路径
    hash: str               # 内容哈希（去重 + 缓存寻址）
    width: int
    height: int
    thumbnail: str          # 缩略图路径
    tags: list[str]         # 多维正交分类
    parent_id: str | None   # 血缘：上游素材
    provenance: dict        # 生成它的工作流 id + 参数快照
    created_at: datetime
```

### 6.4 分类用标签，不用文件夹树

一个素材带正交标签，可多维筛选：

```
["char:knight", "action:walk", "dir:dir1-SW", "stage:final"]
```

- 看 Knight 所有素材 → 筛 `char:knight`
- 看所有 walk 成品 → 筛 `action:walk AND stage:final`

物理存储可用文件夹，逻辑分类靠标签。

### 6.5 血缘（Lineage）—— 隐藏的杀手锏

```
原型图(uploaded) → 生成帧(generated) → 去背(derived) → 精灵表(derived)
```

- **可溯源**：点开成品回看它从哪来、经过什么处理、什么参数
- **可重新派生**：换原型后，引擎顺血缘知道哪些下游失效，一键重跑

血缘 + content hash = 增量重生成，与引擎缓存机制天然打通。

### 6.6 存储布局（本地 SQLite 方案）

```
project_assets/
├── assets.db              # Asset 表 + tags 表 + asset_tags 关联表
├── uploaded/              # 用户上传
├── generated/<hash>.png   # AI 生成（hash 命名，天然去重）
├── derived/<hash>.png     # 派生产物
├── thumbnails/            # 256px 缩略图（列表展示，不加载原图）
└── exports/               # 最终导出（对接 yqcr 目录）
```

### 6.7 数据库 Schema

```sql
CREATE TABLE assets (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    source      TEXT NOT NULL,
    uri         TEXT NOT NULL,
    hash        TEXT NOT NULL,
    width       INTEGER,
    height      INTEGER,
    thumbnail   TEXT,
    parent_id   TEXT REFERENCES assets(id),
    provenance  TEXT,              -- JSON
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_assets_hash ON assets(hash);

CREATE TABLE tags (
    id    INTEGER PRIMARY KEY,
    name  TEXT UNIQUE NOT NULL     -- "char:knight"
);

CREATE TABLE asset_tags (
    asset_id  TEXT REFERENCES assets(id),
    tag_id    INTEGER REFERENCES tags(id),
    PRIMARY KEY (asset_id, tag_id)
);
```

### 6.8 上传处理流水线（Ingest Pipeline）

```
1. 校验      格式/尺寸/通道（是否带透明）
2. 哈希去重  传过的不再存第二份
3. 规格化    统一色彩空间、可选 resize
4. 缩略图    生成 256px 预览
5. 元数据    抽取尺寸/EXIF
6. 入库      写 Asset 记录 + 落盘
```

---

## 7. 工作流格式

工作流以 JSON/YAML 描述（画布 UI 是它的可视化编辑器，但格式本身可手写）：

```yaml
# workflow: knight_8dir_walk.yaml
version: 1
name: "Knight 8方向走路"
nodes:
  - id: load_proto
    type: LoadAsset
    params: { asset_id: "knight_proto_001" }

  - id: fanout
    type: Fanout8Dir
    inputs: { image: load_proto.image }

  - id: gen
    type: Img2Img
    inputs: { image: fanout.batch }
    params:
      prompt: "knight walking, {dir} facing, pixel art, 32x32"
      capability: img2img        # 路由层据此选 provider

  - id: rmbg
    type: RemoveBG
    inputs: { image: gen.image }

  - id: align
    type: BBoxAlign
    inputs: { image: rmbg.image }
    params: { anchor: "bottom_center" }

  - id: quant
    type: QuantizePalette
    inputs: { image: align.image }
    params: { colors: 32 }

  - id: pack
    type: PackGrid
    inputs: { image: quant.image }
    params: { columns: 8 }

  - id: export
    type: ExportYqcr
    inputs: { spritesheet: pack.sheet }
    params:
      character: knight
      action: walk
      target_dir: "/Users/tanli/Documents/godot-code/yqcr/..."
```

---

## 8. API 设计（FastAPI）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/workflows` | POST | 提交工作流执行，返回 run_id |
| `/runs/{id}` | GET | 轮询执行状态/进度 |
| `/runs/{id}/events` | GET (SSE) | 实时进度流 |
| `/assets` | GET | 查询素材库（支持 tag 筛选） |
| `/assets` | POST | 上传素材（走 Ingest） |
| `/assets/{id}` | GET | 获取素材详情 + 血缘 |
| `/nodes` | GET | 列出所有可用节点 + schema（供画布渲染） |
| `/providers` | GET | 列出 provider 及能力 |
| `/routing` | GET/PUT | 读写能力路由表 |

执行异步化：提交返回 run_id，通过轮询或 SSE 跟踪进度。

---

## 9. 架构决策记录（ADR）

### ADR-1：自研极简引擎，不用 Airflow/Dagster
- **决策**：自研 ~500 行图引擎
- **理由**：那些为分布式数据工程设计，过重。我们要的是 ComfyUI 那种单机、内存传图、缓存友好的轻引擎
- **取舍**：放弃开箱即用的分布式（单机不需要）
- **参考**：ComfyUI 的 `execution.py`

### ADR-2：节点用函数 + 装饰器，不用类继承
- **决策**：`@node` 装饰函数，引擎从类型注解抽端口
- **理由**：写新节点只需几行，生态才能繁荣
- **取舍**：复杂节点留 class 逃生舱口

### ADR-3：节点间传内存对象，不传文件路径
- **决策**：传 PIL.Image/np.array，引擎统一托管落盘缓存
- **理由**：节点代码干净；缓存层集中管理
- **取舍**：大批量时内存峰值（lazy + 分块缓解；百张级无压力）

### ADR-4：先引擎 + 配置编排，画布 UI 最后做
- **决策**：先 YAML 工作流跑通，再做 React Flow 画布
- **理由**：画布最贵、最不影响核心价值；先能用再好用
- **取舍**：早期牺牲视觉爽感

### ADR-5：能力路由而非 Key 路由
- **决策**：节点声明 capability，路由层映射到 provider
- **理由**：换后端/换 key/加 provider 三件事解耦（开闭原则）
- **取舍**：多一层抽象，但收益远大于成本

---

## 10. 演进路线（不一步到位，每阶段有可交付价值）

| 阶段 | 内容 | 可交付 |
|------|------|--------|
| **MVP-1** | 引擎内核 + 5 个核心节点 + YAML 编排 | 产出第一张 8 方向精灵表 |
| **MVP-2** | 缓存 + batch fanout + 后端适配层 | 改参数秒级重跑，本地/API 可切 |
| **MVP-3** | 素材中枢（SQLite + 标签 + 血缘）+ Ingest | 上传/选择/溯源 |
| **MVP-4** | FastAPI 服务 + 进度/重试 + 路由配置 | 可远程调、看进度、配路由 |
| **MVP-5** | React Flow 节点画布 + 素材库 UI | 可视化拖拽编排 |
| **MVP-6** | 节点市场 / 工作流模板 | 沉淀可复用资产 |

> MVP-1 大约一两天就能产出第一张可用素材。

---

## 11. 复用开源资产建议

| 项目 | 复用价值 |
|------|---------|
| **ComfyUI** `execution.py` | 引擎内核的最佳范本（拓扑排序+缓存） |
| **agent-sprite-forge** | 后处理脚本：chroma-key 去背、帧切分、包围盒对齐 |
| **falsprite / 302Sprite** | 前端控制台骨架、provider 调用封装参考 |
| **rembg** | 本地去背景 provider |
| **React Flow** | 节点画布前端 |

---

## 12. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 8 方向角色一致性差 | 参考图 + LLM 锁定描述 + 固定 seed；必要时单方向生成镜像翻转 |
| AI 生成成本累积 | 缓存 + 本地 provider 优先 + 批量预估成本 |
| M4 16G 跑不动视频模型 | 视频类走 API（Seedance）；本地只跑图像类（SDXL/rembg） |
| 后处理对齐抖动 | BBoxAlign 节点统一锚点对齐 |
| 范围蔓延 | 严守演进路线，画布等后期；非目标清单兜底 |

---

_文档结束 · 等待反馈后迭代_
