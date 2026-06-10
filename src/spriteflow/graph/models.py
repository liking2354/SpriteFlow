"""管线图数据模型 — JSON 可持久化的 ComfyUI 风格节点图"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PipelineNodeModel(BaseModel):
    """管线图中的业务节点

    每个节点对应一个管道阶段（模板驱动）：
      CharacterMaster  → 角色母版（template_ids → text2img → remove_bg → align）
      DirectionVariant → 方向变体（upstream image + direction templates → img2img）
      AnimationSprite  → 动画精灵（upstream image + action templates → sequential/images）
    """

    id: str = Field(..., description="画布内唯一 ID")
    type: str = Field(..., description="节点类型名")
    x: float = Field(default=0, description="画布坐标 X")
    y: float = Field(default=0, description="画布坐标 Y")
    width: float | None = Field(default=None, description="节点宽度（像素）")
    height: float | None = Field(default=None, description="节点高度（像素）")
    collapsed: bool = Field(default=False, description="节点是否折叠")
    params: dict[str, Any] = Field(default_factory=dict, description="节点参数（影响执行结果）")
    ui: dict[str, Any] = Field(default_factory=dict, description="UI 扩展字段（颜色/备注/分组等，不影响执行）")


class GraphEdgeModel(BaseModel):
    """管线图中的连线"""

    id: str = Field(..., description="连线唯一 ID")
    src_node: str = Field(..., description="上游节点 ID")
    src_port: str = Field(..., description="上游输出端口名")
    dst_node: str = Field(..., description="下游节点 ID")
    dst_port: str = Field(..., description="下游输入端口名")


class PipelineGraphModel(BaseModel):
    """完整管线图定义"""

    schema_version: int = Field(default=1, description="图格式版本（用于未来迁移）")
    id: str = Field(default_factory=lambda: _short_uuid(), description="图唯一 ID")
    name: str = Field(default="", description="图名称")
    description: str = Field(default="", description="描述")
    spec_id: str | None = Field(default=None, description="全局规格书 ID，节点可覆盖")
    nodes: list[PipelineNodeModel] = Field(default_factory=list)
    edges: list[GraphEdgeModel] = Field(default_factory=list)
    viewport: dict[str, Any] = Field(default_factory=dict, description="画布视口状态: {x, y, zoom}")
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )


class GraphIndexEntry(BaseModel):
    """index.json 中的一条索引"""

    id: str
    name: str
    description: str
    tags: list[str]
    node_count: int
    updated_at: str


class GraphIndex(BaseModel):
    """graphs/index.json 的结构"""

    graphs: list[GraphIndexEntry] = Field(default_factory=list)


def _short_uuid() -> str:
    import uuid
    return uuid.uuid4().hex[:8]
