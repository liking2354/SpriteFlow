"""模板系统数据模型 — SpriteSpec / PromptLayer / PromptBlock / CharacterTemplate 等

模板分层结构：
  PromptBlock（最小单元：一段固定 Prompt 文本）
    ↓ 多个合并
  PromptLayer（图层：风格层 / 约束层 / 包围盒层）
    ↓ 多个叠加
  PromptAssembly（一次拼装 = Spec固定层 + 角色层 + 动作层 + 约束层）
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ============================ 枚举 ============================

class BlockCategory(str, Enum):
    """Prompt 子块的语义分类"""
    STYLE = "style"                 # 画风/像素/光照
    PERSPECTIVE = "perspective"     # 视角/摄像机
    PROPORTION = "proportion"       # 头身比/占格
    CONSTRAINT = "constraint"       # 包围盒/尺寸/密度
    BACKGROUND = "background"       # 背景色/无阴影
    QUALITY = "quality"             # 质量关键词
    NEGATIVE = "negative"           # 负面提示词
    CUSTOM = "custom"               # 自定义


class LayerCategory(str, Enum):
    """Prompt 图层的分类"""
    FIXED = "fixed"                 # 固定模板（永不变化）
    SPEC_DEFAULT = "spec_default"   # 规格书默认层
    CHARACTER = "character"         # 角色定义
    ACTION = "action"               # 动作定义
    CONSTRAINT = "constraint"       # 约束层
    CUSTOM = "custom"               # 自定义附加层


class ActionType(str, Enum):
    """动作类型"""
    IDLE = "idle"
    WALK = "walk"
    RUN = "run"
    CAST = "cast"
    ATTACK = "attack"
    HIT = "hit"
    DEATH = "death"
    SPECIAL = "special"             # 特殊技能动作


class SpriteFormat(str, Enum):
    """精灵导出格式"""
    GODOT = "godot"                 # AnimatedSprite
    UNITY = "unity"                 # SpriteRenderer
    PHASER = "phaser"               # spritesheet + atlas
    GENERIC = "generic"             # 纯 PNG + JSON
    COCOS = "cocos"                 # Cocos2d


# ============================ 模板核心模型 ============================

class PromptBlock(BaseModel):
    """Prompt 最小单元 — 一段固定文本 + 语义标签"""
    id: str = Field(default_factory=lambda: f"pb_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    name: str = ""                    # 人类可读名称，如"像素尺寸约束"
    content: str = ""                 # 实际 Prompt 文本
    category: BlockCategory = BlockCategory.CUSTOM
    description: str = ""             # 说明这段 Prompt 的作用
    sort_order: int = 0               # 在同层内的排序
    enabled: bool = True              # 是否启用（调试时可临时关掉）
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class PromptLayer(BaseModel):
    """Prompt 图层 — 多个 PromptBlock 的组合"""
    id: str = Field(default_factory=lambda: f"pl_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    name: str = ""                    # 如"固定风格层"
    category: LayerCategory = LayerCategory.CUSTOM
    description: str = ""
    blocks: list[PromptBlock] = Field(default_factory=list)
    sort_order: int = 0               # 在最终拼装时的顺序（风格 → 角色 → 动作 → 约束）
    enabled: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class CharacterTemplate(BaseModel):
    """角色定义模板 — 第二层 Prompt 的来源"""
    id: str = Field(default_factory=lambda: f"char_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    name: str = ""                    # "剑士" / "法师"
    key: str = ""                     # 英文 key: "warrior" / "mage"
    description: str = ""             # 角色 Prompt 文本
    color_scheme: list[str] = Field(default_factory=list)  # ["#C0392B", "#F1C40F"]
    build_type: str = ""              # "muscular" / "slim" / "athletic" / "massive"
    class_type: str = ""              # "warrior" / "mage" / "assassin" / "priest" / "archer" / "boss" / "npc"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)  # 扩展字段
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ActionTemplate(BaseModel):
    """动作定义模板 — 第三层 Prompt 的来源"""
    id: str = Field(default_factory=lambda: f"act_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    name: str = ""                    # "待机动画"
    key: str = ""                     # "idle" / "walk" / "cast"
    action_type: ActionType = ActionType.IDLE
    prompt: str = ""                  # 动作 Prompt 文本
    directions: int = 4               # 方向数
    frames_per_direction: int = 4     # 每方向帧数
    total_frames: int = 16            # 总帧数
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class VFXTemplate(BaseModel):
    """技能特效模板 — 与角色完全解耦"""
    id: str = Field(default_factory=lambda: f"vfx_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    name: str = ""                    # "火球术"
    key: str = ""                     # "fireball"
    vfx_type: str = ""                # "projectile" / "aoe" / "buff" / "self_cast" / "explosion"
    prompt: str = ""                  # 特效 Prompt 文本
    frames: int = 8                   # 帧数
    canvas_width: int = 128
    canvas_height: int = 128
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class StagePipeline(BaseModel):
    """阶段管线模板 — 串联各阶段的标准生产流程"""
    id: str = Field(default_factory=lambda: f"pipeline_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    name: str = ""                    # "RPG角色完整管线"
    description: str = ""
    spec_id: str = ""                 # 关联的 SpriteSpec
    stages: list[StageDef] = Field(default_factory=list)
    pause_at_stages: list[str] = Field(default_factory=list)  # 哪些阶段需要人工确认
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class StageDef(BaseModel):
    """管线中的一个阶段"""
    id: str = Field(default_factory=lambda: f"stage_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    name: str = ""                    # "角色母版"
    stage_order: int = 0
    action_template_id: str = ""      # 关联的动作模板
    requires_approval: bool = True    # 是否需要人工选优
    generate_count: int = 4           # 生成候选数量
    output_tag: str = ""              # 输出 tag 标记，如 "stage:master"
    extra_prompt: str = ""            # 额外附加的 Prompt
    enabled: bool = True


# ============================ SpriteSpec 规格书 ============================

class AlignRule(BaseModel):
    """对齐规则"""
    auto_center: bool = True
    auto_crop: bool = True
    bottom_align: bool = True         # 底部对齐（踩地）
    detect_threshold: int = 32        # 透明检测阈值
    padding: int = 8                  # 裁剪后边距


class CanvasSpec(BaseModel):
    """画布规格"""
    width: int = 64
    height: int = 64
    target_height_px: int = 48        # 角色目标高度
    target_width_px: int = 28         # 角色目标宽度
    max_colors: int = 24
    outline_style: str = "dark"


class SpriteSpec(BaseModel):
    """角色规格书 — 批量生产的统一标准

    这是整个模板系统的顶层配置，决定了所有产出的尺寸和风格。
    """
    id: str = Field(default_factory=lambda: f"spec_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    name: str = ""
    description: str = ""

    # 画布 + 对齐
    canvas: CanvasSpec = Field(default_factory=CanvasSpec)
    align: AlignRule = Field(default_factory=AlignRule)

    # Prompt 图层列表（按 sort_order 排序后拼装）
    layers: list[PromptLayer] = Field(default_factory=list)

    # 输出配置
    default_format: SpriteFormat = SpriteFormat.GODOT
    default_group_id: str | None = None

    # 关联的模板引用（可选，方便下拉选择）
    default_character_template_ids: list[str] = Field(default_factory=list)
    default_action_template_ids: list[str] = Field(default_factory=list)

    # 元数据
    version: int = 1
    is_active: bool = True            # 是否激活（多版本共存时用）
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ============================ Prompt 拼装模型 ============================

class PromptAssembly(BaseModel):
    """一次 Prompt 拼装请求"""
    spec_id: str = ""                 # 规格书
    character_template_id: str = ""   # 角色模板
    action_template_id: str = ""      # 动作模板
    override_char_desc: str | None = None   # 覆盖角色描述（临时调试用）
    override_action_prompt: str | None = None  # 覆盖动作 Prompt
    extra_layers: list[str] = Field(default_factory=list)  # 额外附加图层文本
    extra_negative: str | None = None        # 额外负面提示词


class PromptAssemblyResult(BaseModel):
    """Prompt 拼装结果 — 前端预览用"""
    layers: list[PromptLayerInfo] = Field(default_factory=list)  # 各层拆分展示
    final_prompt: str = ""            # 完整拼装后的 Prompt
    final_negative: str = ""          # 完整负面提示词
    spec_id: str = ""
    character_name: str = ""
    action_name: str = ""


class PromptLayerInfo(BaseModel):
    """一层 Prompt 的展示信息"""
    layer_name: str = ""
    category: LayerCategory = LayerCategory.CUSTOM
    blocks: list[BlockInfo] = Field(default_factory=list)
    combined: str = ""                # 该层拼装后的文本


class BlockInfo(BaseModel):
    """一个 Block 的展示信息"""
    block_name: str = ""
    category: BlockCategory = BlockCategory.CUSTOM
    content: str = ""
    enabled: bool = True


# ============================ 批量生成模型 ============================

class BatchGenerateRequest(BaseModel):
    """批量生成请求"""
    spec_id: str = ""
    pipeline_id: str | None = None    # 可选管线模板
    character_template_ids: list[str] = Field(default_factory=list)
    action_template_ids: list[str] = Field(default_factory=list)
    vfx_template_ids: list[str] = Field(default_factory=list)
    generate_count_per: int = 4       # 每个组合生成候选数
    concurrent: int = 4               # 并发数
    group_id: str | None = None


class BatchGenerateResponse(BaseModel):
    """批量生成响应"""
    batch_id: str = ""
    total_jobs: int = 0
    jobs: list[dict[str, Any]] = Field(default_factory=list)  # 精简 job 列表
    status: str = "started"
