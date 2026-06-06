# SpriteFlow 开发计划

> 最后更新：2026-06-06
> 总进度：3 / 10 Phase 完成

---

## Phase 1 — 模板系统后端集成

**目标**：让模板系统跑起来，可 CRUD、可预览  
**预计**：1天 | **状态**：✅ 已完成

- [x] 1.1 在 `app.py` lifespan 中初始化 `TemplateDB`、建表、注册到 deps
- [x] 1.2 挂载 `templates_router` 到 FastAPI app
- [x] 1.3 注入预置数据（1 Spec + 6 角色 + 7 动作 + 4 VFX）
- [x] 1.4 `/api/templates/preview` 集成测试（Spec + 剑士 + 待机 → 验证拼装结果）

**验收**：`curl /api/templates/specs` 返回 1 个 Spec、`/api/templates/characters` 返回 6 个角色、`/api/templates/preview` 返回正确的三层拼装 Prompt ✅

**修改文件**：
- `src/spriteflow/templates/db.py` — 增加 `connect()/close()` 方法
- `src/spriteflow/api/deps.py` — 添加 `_template_db` 单例 + getter/setter
- `src/spriteflow/templates/api.py` — 改用 deps 单例，修正 prefix 为 `/templates`
- `src/spriteflow/templates/__init__.py` — 导出 get_template_db/set_template_db
- `src/spriteflow/templates/builder.py` — 修复 `@staticmethod` 中 `self` 引用
- `src/spriteflow/api/app.py` — lifespan 初始化 + router 挂载

---

## Phase 2 — SpriteAligner 后处理管线

**目标**：解决 42px vs 53px 尺寸不一致问题  
**预计**：1天 | **状态**：✅ 已完成

- [x] 2.1 实现 `SpriteAligner.align()` 核心逻辑（检测 → 裁剪 → 缩放 → 居中 → 底部对齐）
- [x] 2.2 注册 `SpriteAlignNode` 到节点系统
- [x] 2.3 在 `example_text2img_with_align.yaml` 流程中插入 Align 节点，验证输出尺寸统一

**验收**：同一 Spec 下任意尺寸输入图，经 Aligner 处理后全部落在 64×64 画布内 ✅（4 种不同输入尺寸全部输出 64x64）

**修改文件**：
- `src/spriteflow/engine/sprite_aligner.py` — 新建，核心对齐逻辑（detect_bounds / crop_to_sprite / scale_to_fit / place_on_canvas / align）
- `src/spriteflow/nodes/sprite_align.py` — 新建，SpriteAlignNode 封装
- `src/spriteflow/nodes/__init__.py` — 注册 SpriteAlign 节点
- `workflows/example_text2img_with_align.yaml` — 新建，含 SpriteAlign 的完整工作流

**验收**：同一 Spec 下生成 5 张图，经 Aligner 处理后全部落在 64×64 画布内，角色高度误差 < 3px

---

## Phase 3 — OpenRouter Provider

**目标**：统一路由层，按场景选最优模型  
**预计**：1天 | **状态**：✅ 已完成

- [x] 3.1 实现 `OpenRouterProvider`（OpenAI 兼容 API，`POST /chat/completions`，`modalities: ["image", "text"]`）
- [x] 3.2 在 `routing.yaml` 中新增路由：`character_master → openrouter`、`four_view → openrouter`，并添加 text2img/img2img 的 openrouter 回退链
- [x] 3.3 OpenRouter 支持模型参数覆盖：`POST /api/generate` 时可通过 `model` 字段切换
- [x] 3.4 注册到 `app.py` lifespan 并验证（提供者注册、路由配置、能力枚举扩展全部通过）

**验收**：
- OpenRouterProvider 支持 TEXT2IMG / IMG2IMG / CHARACTER_MASTER / FOUR_VIEW 四种能力 ✅
- routing.yaml 13 条路由 + 2 条回退链正确加载 ✅
- `POST /api/generate` 支持 `model` 参数覆盖（如 `openai/gpt-image-1`）✅
- 场景默认模型：`character_master` → `openai/gpt-image-1`，`four_view` → `bytedance/doubao-seedream-4.5` ✅

**修改文件**：
- `src/spriteflow/providers/openrouter.py` — 新建，OpenRouter OpenAI-compatible API 适配器
- `src/spriteflow/providers/base.py` — 新增 `CHARACTER_MASTER` / `FOUR_VIEW` 能力枚举
- `src/spriteflow/providers/__init__.py` — 导出 `OpenRouterProvider`
- `config/routing.yaml` — 新增 character_master/four_view 路由 + text2img/img2img 回退链 + openrouter 凭证
- `src/spriteflow/config.py` — 新增 `openrouter_api_key` / `openrouter_default_model` / `openrouter_base_url`
- `src/spriteflow/api/app.py` — lifespan 中注册 OpenRouterProvider + 凭证
- `src/spriteflow/api/generate.py` — `GenerateRequest` 新增 `model` 字段并传递到 payload
- `.env.example` — 新增 OpenRouter 环境变量模板

---

## Phase 4 — ExtractFrames + PackSpritesheet 节点  🔑

> 🔑 **关键里程碑**：首次打通"视频 → 精灵表"完整链路

**目标**：视频生成 → 精灵帧 → 精灵表 完整链路  
**预计**：2天 | **状态**：⬜ 未开始

- [ ] 4.1 实现 `ExtractFramesNode`（视频 → ffmpeg 抽帧 → 逐帧 rembg → SpriteAligner）
- [ ] 4.2 实现 `PackSpritesheetNode`（帧列表 → 拼合大图 + atlas JSON，支持 Godot/Unity/Phaser 格式）
- [ ] 4.3 编写验证工作流：`生成走路视频 → 抽帧 → 对齐 → 拼合 → 导出`
- [ ] 4.4 前端 AssetPreviewModal 中增加帧序列播放功能（canvas 逐帧循环）

**验收**：一张 128×128 角色走路精灵表 + atlas.json，导入 Godot 能直接创建 AnimatedSprite

---

## Phase 5 — 模板驱动的生成链路  🔑

> 🔑 **关键里程碑**：模板驱动生成跑通，后续工作在此基础上扩展

**目标**：生成请求不再手写 prompt，而是选 Spec + 角色 + 动作  
**预计**：2天 | **状态**：⬜ 未开始

- [ ] 5.1 `GenerateRequest` 新增 `spec_id`、`character_template_id`、`action_template_id` 可选字段
- [ ] 5.2 `generate.py` 中，若提供模板参数，用 `PromptBuilder` 拼装 prompt 替代原始 prompt
- [ ] 5.3 生成结果自动打 tag：`stage:master` / `stage:walk` / `char:warrior` / `spec:rpg_chibi`
- [ ] 5.4 支持"基于上一阶段最佳结果"：`ref_asset_ids` + 当前阶段 prompt → img2img

**验收**：选 Spec + 剑士 + 待机 → 一键生成 4 张候选 → 选一张设为 next_ref → 走路阶段基于它生成

---

## Phase 6 — 批量生成引擎

**目标**：角色 × 阶段 矩阵式批量生产  
**预计**：1天 | **状态**：⬜ 未开始

- [ ] 6.1 实现 `POST /api/generate/batch` 端点，接收 `BatchGenerateRequest`
- [ ] 6.2 内部展开为 `char × action` 矩阵，每个组合创建一个 GenerationJob
- [ ] 6.3 并发控制：信号量限制同时进行的 Seedance 任务数（视频生成资源消耗大）
- [ ] 6.4 批量生成状态汇总：`GET /api/generate/batch/{batch_id}` 返回进度矩阵

**验收**：3 角色 × 2 动作 = 6 个任务并发执行 → 完成后 6 个 job 都是 completed 状态

---

## Phase 7 — 前端模板管理页面

**目标**：可视化管理所有模板，不再改代码  
**预计**：2天 | **状态**：⬜ 未开始

- [ ] 7.1 `/specs` 页面 — Spec 列表 + Spec 编辑器（画布参数 + 图层/Block CRUD + 拖拽排序 + Prompt 预览）
- [ ] 7.2 `/characters` 页面 — 角色卡片库 + 新增/编辑角色弹窗
- [ ] 7.3 `/actions` 页面 — 动作卡片库（同角色页类似）
- [ ] 7.4 Block 内联编辑器组件 — 双击展开、编辑 Prompt 文本、保存/取消
- [ ] 7.5 Prompt 实时预览组件 — 左下角固定面板，实时显示三层拼装结果

**验收**：改固定风格层一个词 → 预览区即时刷新 → 生成测试 → 效果符合预期

---

## Phase 8 — 批量生成页面

**目标**：选模板 → 勾选 → 一键批量产出  
**预计**：1天 | **状态**：⬜ 未开始

- [ ] 8.1 `/batch` 页面 — 选 Spec + 多选角色 + 多选动作 → 实时计算总任务数
- [ ] 8.2 批量任务监控面板 — 进度矩阵（角色×动作 grid，每格显示 pending/running/completed/failed）
- [ ] 8.3 支持"只跑未完成的"和"全部重跑"
- [ ] 8.4 生成结果自动归入对应 Group（按角色分组）

**验收**：勾选 4 角色 × 3 动作 = 12 个任务 → 10 分钟内全部完成 → 每个角色获得独立 Group

---

## Phase 9 — 技能特效生产管线

**目标**：技能和角色彻底分离  
**预计**：1天 | **状态**：⬜ 未开始

- [ ] 9.1 实现 `VFXTemplate` 驱动的生成：选技能模板 → 生成多帧 → 打包
- [ ] 9.2 VFX 的 SpriteSpec 独立于角色（画布 128×128，无需去背景约束）
- [ ] 9.3 前端 `/vfx` 页面 → 选火球术 → 一键生成 8 帧 → 预览播放

**验收**：独立生成火球术 8 帧 → 打包 spriteSheet → 所有角色共用

---

## Phase 10 — 全链路联调 + 优化

**目标**：端到端验证 + 稳定性  
**预计**：1天 | **状态**：⬜ 未开始

- [ ] 10.1 端到端走通：选 Spec → 剑士母版 → 选优 → 走路视频 → 抽帧 → 精灵表 → 导入 Godot
- [ ] 10.2 角色一致性回归测试：同一角色 walk → run → cast 阶段间角色外观是否漂移
- [ ] 10.3 性能优化：缓存层、并发数调优、大尺寸视频下载超时处理
- [ ] 10.4 错误处理：API 密钥失效提示、内容审核拦截友好提示、重试策略

---

## 总览

```
Phase 3  ████████████████████████████ OpenRouter        (4/4)  ✅
Phase 4  ░░░░░░░░░░░░░░░░░░░░░░░░░░ Extract+Pack      (0/4)  ⬜  🔑
Phase 5  ░░░░░░░░░░░░░░░░░░░░░░░░░░ 模板驱动生成       (0/4)  ⬜  🔑
Phase 6  ░░░░░░░░░░░░░░░░░░░░░░░░░░ 批量生成引擎       (0/4)  ⬜
Phase 7  ░░░░░░░░░░░░░░░░░░░░░░░░░░ 前端模板管理       (0/5)  ⬜
Phase 8  ░░░░░░░░░░░░░░░░░░░░░░░░░░ 前端批量生成       (0/4)  ⬜
Phase 9  ░░░░░░░░░░░░░░░░░░░░░░░░░░ 技能特效管线       (0/3)  ⬜
Phase 10 ░░░░░░░░░░░░░░░░░░░░░░░░░░ 全链路联调         (0/4)  ⬜
         ─────────────────────────────────────────────
         全部 39 个任务，预计 13 天
```

- 🔑 = 关键里程碑，完成后后续 Phase 可并行推进
- 顺序执行 13 天，部分并行可压缩到 10 天
