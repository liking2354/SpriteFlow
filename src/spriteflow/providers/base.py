"""Provider 基类 + Capability 枚举 + Credential 数据类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Capability(str, Enum):
    """能力枚举：节点声明需要的能力类型"""

    TEXT2IMG = "text2img"
    IMG2IMG = "img2img"
    MULTI_IMAGE_FUSION = "multi_image_fusion"
    SEQUENTIAL_IMAGES = "sequential_images"
    TEXT2VIDEO = "text2video"
    IMG2VIDEO = "img2video"
    REMOVE_BG = "remove_bg"
    EXTRACT_FRAMES = "extract_frames"
    # 火山引擎 AI MediaKit 图像处理能力
    ENHANCE_PHOTO = "enhance_photo"       # 图像画质增强
    IMAGE_INPAINT = "image_inpaint"         # 图像擦除修复
    IMAGE_OUTPAINT = "image_outpaint"       # 智能扩图
    IMAGE_CUT = "image_cut"                 # 图像智能裁剪
    SLIM_IMAGE = "slim_image"               # 集智瘦身
    RESIZE_IMAGE = "resize_image"            # 图像缩放


@dataclass
class Credential:
    """访问凭证"""

    provider_name: str
    api_key: str = ""
    extra: dict[str, Any] | None = None


class Provider(ABC):
    """Provider 抽象基类

    子类需实现：
      - name: str               provider 名称
      - capabilities: set[Capability]  支持的能力
      - invoke(cap, payload, cred)      调用逻辑
    """

    name: str = "unknown"
    capabilities: set[Capability] = set()

    @abstractmethod
    async def invoke(
        self,
        cap: Capability,
        payload: dict[str, Any],
        cred: Credential,
    ) -> dict[str, Any]:
        """调用能力

        Args:
            cap: 要调用的能力
            payload: 调用参数（prompt、image、strength 等）
            cred: 访问凭证

        Returns:
            结果字典（至少包含 "data" 或 "image" 等）
        """
        ...

    def supports(self, cap: Capability) -> bool:
        """检查是否支持某能力"""
        return cap in self.capabilities
