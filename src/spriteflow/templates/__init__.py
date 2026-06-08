"""模板系统 — 统一 PromptTemplate 管理

单表模型 + 拼装引擎 + REST API
"""

from .models import (
    PromptTemplate, PromptSlot, TemplateType, SlotType,
    TemplatePreviewRequest, TemplatePreviewResult,
)
from .db import TemplateDB, TEMPLATE_SCHEMA_DDL
from .builder import assemble_prompt, preview_prompt
from .seed import PRESET_TEMPLATES, PRESET_BY_ID
from .api import router as templates_router
from ..api.deps import get_template_db, set_template_db

__all__ = [
    "PromptTemplate", "PromptSlot", "TemplateType", "SlotType",
    "TemplatePreviewRequest", "TemplatePreviewResult",
    "TemplateDB", "TEMPLATE_SCHEMA_DDL",
    "assemble_prompt", "preview_prompt",
    "PRESET_TEMPLATES", "PRESET_BY_ID",
    "templates_router", "get_template_db", "set_template_db",
]
