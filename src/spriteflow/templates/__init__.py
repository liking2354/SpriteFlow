"""模板系统 — SpriteSpec / Prompt 图层 / 角色 / 动作 / VFX / 管线 管理"""

from .models import (
    SpriteSpec, PromptLayer, PromptBlock, BlockCategory, LayerCategory,
    CharacterTemplate, ActionTemplate, ActionType, VFXTemplate,
    StagePipeline, StageDef, CanvasSpec, AlignRule, SpriteFormat,
    PromptAssembly, PromptAssemblyResult,
    BatchGenerateRequest, BatchGenerateResponse,
)
from .db import TemplateDB, TEMPLATE_SCHEMA_DDL
from .builder import PromptBuilder
from .api import router as templates_router, set_template_db

__all__ = [
    "SpriteSpec", "PromptLayer", "PromptBlock", "BlockCategory", "LayerCategory",
    "CharacterTemplate", "ActionTemplate", "ActionType", "VFXTemplate",
    "StagePipeline", "StageDef", "CanvasSpec", "AlignRule", "SpriteFormat",
    "PromptAssembly", "PromptAssemblyResult",
    "BatchGenerateRequest", "BatchGenerateResponse",
    "TemplateDB", "TEMPLATE_SCHEMA_DDL",
    "PromptBuilder",
    "templates_router", "set_template_db",
]
