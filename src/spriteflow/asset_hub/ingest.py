"""Ingest Pipeline — 上传处理流水线"""

from __future__ import annotations

import hashlib
import io
from typing import BinaryIO

from PIL import Image

from .models import Asset
from .db import AssetDB
from ..storage.base import StorageBackend, StoragePrefix


def compute_content_hash(data: bytes) -> str:
    """计算文件内容的 SHA256 哈希"""
    return hashlib.sha256(data).hexdigest()[:32]


def generate_thumbnail(image: Image.Image, size: int = 256) -> Image.Image:
    """生成缩略图"""
    image = image.copy()
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    return image


def normalize_image(image: Image.Image) -> Image.Image:
    """规格化图像：统一 RGBA 色彩空间"""
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return image


class IngestPipeline:
    """上传处理流水线

    流程：校验 → 哈希去重 → 规格化 → 缩略图 → 上传 COS → 写元数据
    """

    def __init__(self, storage: StorageBackend, db: AssetDB) -> None:
        self.storage = storage
        self.db = db

    async def ingest(
        self,
        data: bytes,
        filename: str = "",
        source: str = "uploaded",
        tags: list[str] | None = None,
        parent_id: str | None = None,
        provenance: dict | None = None,
    ) -> Asset:
        """执行上传流水线

        Args:
            data: 原始文件数据
            filename: 原始文件名
            source: 来源类型 uploaded/generated/derived
            tags: 标签列表
            parent_id: 上游素材 id（血缘）
            provenance: 生成溯源信息

        Returns:
            Asset 元数据记录
        """
        # 1. 校验 & 加载
        image = Image.open(io.BytesIO(data))

        # 2. 哈希去重
        content_hash = compute_content_hash(data)
        existing = await self.db.get_asset_by_hash(content_hash)
        if existing:
            return existing  # 已存在，直接返回

        # 3. 规格化
        image = normalize_image(image)
        width, height = image.size

        # 4. 重新编码规格化后的数据
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        normalized_data = buf.getvalue()

        # 去重用规格化后的 hash
        content_hash = compute_content_hash(normalized_data)

        # 5. 缩略图
        thumb = generate_thumbnail(image)
        thumb_buf = io.BytesIO()
        thumb.save(thumb_buf, format="PNG")
        thumb_data = thumb_buf.getvalue()

        # 6. 上传主文件到 COS
        storage_prefix = StoragePrefix(source)
        file_key = f"{content_hash}.png"
        uri = await self.storage.upload(file_key, normalized_data, prefix=storage_prefix)

        # 7. 上传缩略图到 COS
        thumb_key = f"{content_hash}.png"
        thumbnail_uri = await self.storage.upload(
            thumb_key, thumb_data, prefix=StoragePrefix.THUMBNAILS
        )

        # 8. 创建 Asset 记录
        asset = Asset(
            type="image",
            source=source,
            uri=uri,
            hash=content_hash,
            width=width,
            height=height,
            thumbnail=thumbnail_uri,
            tags=tags or [],
            parent_id=parent_id,
            provenance=provenance,
        )

        await self.db.create_asset(asset)
        return asset
