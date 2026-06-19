"""
SpriteFlow 自定义组件模块

提供独立于 AI 模型代理的自定义节点能力。
每个组件有独立的参数 schema 和执行逻辑，通过统一的 Component 基类扩展。

组件分类：
- ai/     : AI 模型类组件（如 Seedance 特定版本）
- image/  : 图片处理类组件
- video/  : 视频处理类组件
- function/: 功能工具类组件

使用方式：
    from spriteflow.components.registry import ComponentRegistry
    schemas = ComponentRegistry.list_schemas()
"""

import logging

from .registry import ComponentRegistry

logger = logging.getLogger(__name__)


def _register_all():
    """注册所有组件"""
    from .ai.seedance_pro_fast import SeedanceProFastComponent
    from .image.image_input import ImageInputComponent
    from .image.remove_bg import RemoveBGComponent
    from .image.sprite_crop import SpriteCropComponent
    from .image.grid_merge import ImageGridMergeComponent
    from .video.frame_extract import VideoFrameExtractComponent

    ComponentRegistry.register(SeedanceProFastComponent())
    ComponentRegistry.register(ImageInputComponent())
    ComponentRegistry.register(RemoveBGComponent())
    ComponentRegistry.register(SpriteCropComponent())
    ComponentRegistry.register(ImageGridMergeComponent())
    ComponentRegistry.register(VideoFrameExtractComponent())


# 模块加载时自动注册
_register_all()
