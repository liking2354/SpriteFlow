"""SpriteAligner — 角色精灵自动对齐器

解决 AI 生成图像尺寸不一致的问题：
（法师 42px 高 vs 刺客 53px 高）

流程：
  1. 检测非透明像素的 bounding box
  2. 裁剪到角色实际区域（可加 padding）
  3. 等比缩放到目标高度/宽度范围内（保持比例）
  4. 居中放置到画布中（底部对齐 / 居中）
  5. 输出统一尺寸的精灵帧
"""

from __future__ import annotations

import numpy as np
from PIL import Image


class SpriteAligner:
    """精灵图像对齐器 — 纯本地 PIL/NumPy 操作，无需远程 API"""

    @staticmethod
    def detect_bounds(
        image: Image.Image,
        threshold: int = 32,
    ) -> tuple[int, int, int, int] | None:
        """检测图像中非透明像素的包围盒

        Returns:
            (left, top, right, bottom) 或 None（如果全是透明像素）
        """
        if image.mode not in ("RGBA", "LA"):
            image = image.convert("RGBA")

        alpha = np.array(image.split()[-1])
        non_transparent = np.where(alpha > threshold)

        if len(non_transparent[0]) == 0:
            return None

        top = int(non_transparent[0].min())
        bottom = int(non_transparent[0].max())
        left = int(non_transparent[1].min())
        right = int(non_transparent[1].max())

        return left, top, right, bottom

    @staticmethod
    def crop_to_sprite(
        image: Image.Image,
        bounds: tuple[int, int, int, int],
        padding: int = 8,
    ) -> Image.Image:
        """按包围盒裁剪，加 padding 留白边"""
        left, top, right, bottom = bounds

        # 加 padding，但不超出图像边界
        w, h = image.size
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(w, right + padding + 1)
        bottom = min(h, bottom + padding + 1)

        return image.crop((left, top, right, bottom))

    @staticmethod
    def scale_to_fit(
        sprite: Image.Image,
        target_width: int,
        target_height: int,
    ) -> Image.Image:
        """等比缩放精灵到目标宽高范围内（保持比例，不超出）"""
        sw, sh = sprite.size

        # 计算缩放比：以高度为基准，但如果宽度超过则进一步缩小
        scale = target_height / sh
        new_w = int(sw * scale)
        new_h = target_height

        if new_w > target_width:
            scale = target_width / new_w
            new_w = target_width
            new_h = int(new_h * scale)

        return sprite.resize((new_w, new_h), Image.LANCZOS)

    @staticmethod
    def place_on_canvas(
        sprite: Image.Image,
        canvas_width: int,
        canvas_height: int,
        center: bool = True,
        bottom_align: bool = True,
    ) -> Image.Image:
        """将精灵放置到目标画布中的指定位置"""
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        sw, sh = sprite.size

        if center:
            x = (canvas_width - sw) // 2
        else:
            x = 0

        if bottom_align:
            y = canvas_height - sh
        else:
            y = (canvas_height - sh) // 2

        canvas.paste(sprite, (x, y), sprite)
        return canvas

    @classmethod
    def align(
        cls,
        image: Image.Image,
        canvas_width: int = 64,
        canvas_height: int = 64,
        target_width: int = 28,
        target_height: int = 48,
        detect_threshold: int = 32,
        padding: int = 8,
        auto_center: bool = True,
        auto_crop: bool = True,
        bottom_align: bool = True,
    ) -> Image.Image:
        """一键对齐：检测 → 裁剪 → 缩放 → 放置

        Args:
            image:           输入 RGBA 图像
            canvas_width:    目标画布宽度
            canvas_height:   目标画布高度
            target_width:    角色在画布中的目标宽度
            target_height:   角色在画布中的目标高度
            detect_threshold: 透明检测阈值（0-255）
            padding:         裁剪后边距
            auto_center:     是否自动水平居中
            auto_crop:       是否自动裁剪（False 则跳过裁剪直接缩放）
            bottom_align:    是否底部对齐

        Returns:
            对齐后的 RGBA 图像，尺寸为 (canvas_width, canvas_height)
        """
        # 确保 RGBA 模式
        if image.mode not in ("RGBA", "LA"):
            image = image.convert("RGBA")

        if auto_crop:
            # 1. 检测角色区域
            bounds = cls.detect_bounds(image, detect_threshold)
            if bounds is None:
                # 全是透明像素，返回空白画布
                return Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

            # 2. 裁剪
            sprite = cls.crop_to_sprite(image, bounds, padding)
        else:
            sprite = image

        # 3. 等比缩放
        sprite = cls.scale_to_fit(sprite, target_width, target_height)

        # 4. 放置到画布
        result = cls.place_on_canvas(
            sprite,
            canvas_width,
            canvas_height,
            center=auto_center,
            bottom_align=bottom_align,
        )

        return result
