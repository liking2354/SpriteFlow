"""模板系统数据模型 — 统一 PromptTemplate 单表模型

所有模版通过 type 字段区分用途，slots 定义前端输入控件。
拼装公式: sorted by type → fill slots → "\n\n".join(texts)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TemplateType(str, Enum):
    SPEC = "spec"
    CHARACTER = "character"
    DIRECTION = "direction"
    ACTION = "action"
    VFX = "vfx"
    CUSTOM = "custom"

    @property
    def sort_priority(self) -> int:
        _order = {self.SPEC: 0, self.CHARACTER: 1, self.DIRECTION: 2,
                  self.ACTION: 3, self.VFX: 4, self.CUSTOM: 5}
        return _order.get(self, 99)


class SlotType(str, Enum):
    INPUT = "input"
    DROPDOWN = "dropdown"


class PromptSlot(BaseModel):
    """模板中的可填充字段 — 前端渲染为 input 或 dropdown"""
    name: str = Field(..., description="字段名，对应 text 中的 {name} 占位符")
    type: SlotType = Field(default=SlotType.INPUT)
    label: str = Field(default="")
    default: str = Field(default="")
    options: list[str] = Field(default_factory=list)
    placeholder: str = Field(default="")


class PromptTemplate(BaseModel):
    """统一 Prompt 模版 — 单表取代旧六层嵌套模型

    text 中使用 {slot_name} 占位符，运行时由 slot_values 填充。
    """
    id: str = Field(default_factory=lambda: f"tmpl_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    name: str = Field(default="")
    type: TemplateType = Field(default=TemplateType.CUSTOM)
    text: str = Field(default="", description="Prompt 文本，使用 {slot_name} 占位符")
    slots: list[PromptSlot] = Field(default_factory=list, description="可填充字段定义")
    description: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class TemplatePreviewRequest(BaseModel):
    """模板拼装预览请求"""
    template_ids: list[str] = Field(default_factory=list)
    slot_values: dict[str, str] = Field(default_factory=dict)


class TemplatePreviewResult(BaseModel):
    """模板拼装预览结果"""
    layers: list[dict[str, Any]] = Field(default_factory=list)
    final_prompt: str = ""
