"""
Component 基类 — 所有自定义组件必须继承此基类

每个 Component 声明自己的 meta（元数据）并实现 execute() 方法。
meta 中包含 input_schema（前端表单）和 param_schema（组件参数），
框架会自动将其转换为 workflow node-schemas 兼容格式。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComponentMeta:
    """组件元数据，用于注册和前端展示"""

    component_id: str           # 唯一标识，如 "seedance-v1-pro-fast"
    display_name: str           # 前端显示名称
    category: str               # 分类: "image", "video", "audio", "text", "function"
    subcategory: str = ""       # 子分类: "generation", "editing", "processing"
    description: str = ""
    version: str = "1.0.0"
    icon: str = ""

    # 用户需要配置的凭据 / 连接参数（运行时从 DB 或 .env 读取）
    credential_schema: dict[str, Any] = field(default_factory=dict)

    # 每次执行时的输入参数 schema（前端表单 → input_params）
    # 格式: JSON Schema properties
    input_schema: dict[str, Any] = field(default_factory=dict)
    input_required: list[str] = field(default_factory=list)

    # 输出类型
    output_type: str = "video_url"  # text | image_url | video_url | audio_url


class Component(ABC):
    """自定义组件基类

    生命周期：
    1. 导入时自动注册到 ComponentRegistry
    2. 前端通过 get_node_schemas() 获取 schema
    3. 运行时调用 execute(inputs, params) 执行
    """

    @property
    @abstractmethod
    def meta(self) -> ComponentMeta:
        """返回组件元数据"""
        ...

    @abstractmethod
    async def execute(
        self,
        inputs: dict[str, Any],
        params: dict[str, Any],
        credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行组件逻辑

        Args:
            inputs: 上游节点传入的数据 {"prompt": "...", "image_url": "..."}
            params: 用户在节点面板配置的参数 {"aspect_ratio": "16:9", ...}
            credentials: 凭据信息 {"api_key": "...", "base_url": "..."}

        Returns:
            符合 workflow 格式的结果:
            {
                "outputs": [{"type": "video_url", "value": "https://..."}],
                "usage": {"model": "...", "tokens": ...}  # 可选
            }
        """
        ...

    async def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        """校验输入参数，返回错误信息列表"""
        return []

    def to_node_schema(self) -> dict[str, Any]:
        """转换为 workflow node-schemas 兼容格式"""
        from .schema_bridge import component_to_node_schema
        return component_to_node_schema(self)
