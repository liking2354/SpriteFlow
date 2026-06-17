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
        group_id: str | None = None,
        provenance: dict | None = None,
    ) -> Asset:
        """执行上传流水线

        Args:
            data: 原始文件数据
            filename: 原始文件名
            source: 来源类型 uploaded/generated/derived
            tags: 标签列表
            parent_id: 上游素材 id（血缘）
            group_id: 归属分组 id
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
            group_id=group_id,
            provenance=provenance,
        )

        await self.db.create_asset(asset)
        return asset

    async def replace(
        self,
        asset_id: str,
        data: bytes,
    ) -> Asset:
        """覆盖原素材内容（保留 id / parent_id / tags / favorite）。

        流程：校验 → 规格化 → 重新计算 hash → 缩略图 → 上传 COS → UPDATE 元数据
        """
        existing = await self.db.get_asset(asset_id)
        if not existing:
            raise ValueError(f"素材不存在: {asset_id}")

        # 1. 解码 + 规格化
        image = Image.open(io.BytesIO(data))
        image = normalize_image(image)
        width, height = image.size

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        normalized_data = buf.getvalue()
        content_hash = compute_content_hash(normalized_data)

        # 2. 缩略图
        thumb = generate_thumbnail(image)
        thumb_buf = io.BytesIO()
        thumb.save(thumb_buf, format="PNG")
        thumb_data = thumb_buf.getvalue()

        # 3. 上传到 COS（按当前 source 决定 prefix；复用 hash 命名让相同内容自然去重）
        storage_prefix = StoragePrefix(existing.source)
        file_key = f"{content_hash}.png"
        uri = await self.storage.upload(file_key, normalized_data, prefix=storage_prefix)
        thumbnail_uri = await self.storage.upload(
            file_key, thumb_data, prefix=StoragePrefix.THUMBNAILS
        )

        # 4. 更新元数据
        await self.db.replace_asset_content(
            asset_id,
            uri=uri,
            hash_=content_hash,
            width=width,
            height=height,
            thumbnail=thumbnail_uri,
        )

        # 5. 返回最新 Asset
        updated = await self.db.get_asset(asset_id)
        assert updated is not None
        return updated

    async def ingest_video(
        self,
        data: bytes,
        *,
        ext: str = "mp4",
        content_type: str = "video/mp4",
        tags: list[str] | None = None,
        parent_id: str | None = None,
        group_id: str | None = None,
        provenance: dict | None = None,
    ) -> Asset:
        """把视频字节直接落库到 COS videos/ 目录，并写一条 type=video 的 Asset。

        视频不做规格化、不生成缩略图（前端用 <video poster> 或首帧异步生成）。
        """
        content_hash = compute_content_hash(data)
        existing = await self.db.get_asset_by_hash(content_hash)
        if existing:
            return existing

        file_key = f"{content_hash}.{ext}"
        uri = await self.storage.upload(
            file_key, data, prefix=StoragePrefix.VIDEOS, content_type=content_type
        )

        asset = Asset(
            type="video",
            source="generated",
            uri=uri,
            hash=content_hash,
            width=None,
            height=None,
            thumbnail=None,
            tags=tags or [],
            parent_id=parent_id,
            group_id=group_id,
            provenance=provenance,
            mime_type=content_type,
        )
        await self.db.create_asset(asset)
        return asset

    async def ingest_text(
        self,
        content: str,
        filename: str = "",
        source: str = "uploaded",
        tags: list[str] | None = None,
        parent_id: str | None = None,
        group_id: str | None = None,
        provenance: dict | None = None,
    ) -> Asset:
        """将文本内容写入 .txt 文件上传存储，并写一条 type=text 的 Asset。

        text_preview 截取前 200 字符。
        """
        data = content.encode("utf-8")
        content_hash = compute_content_hash(data)
        existing = await self.db.get_asset_by_hash(content_hash)
        if existing:
            return existing

        name = filename.rsplit(".", 1)[0] if filename else "text"
        file_key = f"{content_hash}.txt"
        uri = await self.storage.upload(
            file_key, data, prefix=StoragePrefix(source),
            content_type="text/plain; charset=utf-8",
        )

        preview = content[:200] if len(content) > 200 else content

        asset = Asset(
            type="text",
            source=source,
            uri=uri,
            hash=content_hash,
            width=None,
            height=None,
            thumbnail=None,
            tags=tags or [],
            parent_id=parent_id,
            group_id=group_id,
            provenance=provenance,
            text_preview=preview,
            mime_type="text/plain",
        )
        await self.db.create_asset(asset)
        return asset

    async def ingest_audio(
        self,
        data: bytes,
        filename: str = "",
        source: str = "uploaded",
        tags: list[str] | None = None,
        parent_id: str | None = None,
        group_id: str | None = None,
        provenance: dict | None = None,
    ) -> Asset:
        """将音频文件上传存储，并写一条 type=audio 的 Asset。

        从文件扩展名推断 mime_type。
        """
        content_hash = compute_content_hash(data)
        existing = await self.db.get_asset_by_hash(content_hash)
        if existing:
            return existing

        # 从文件名推断扩展名和 MIME 类型
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp3"
        mime_map = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "ogg": "audio/ogg",
            "flac": "audio/flac",
            "aac": "audio/aac",
            "m4a": "audio/mp4",
            "webm": "audio/webm",
        }
        content_type = mime_map.get(ext, "audio/mpeg")

        file_key = f"{content_hash}.{ext}"
        uri = await self.storage.upload(
            file_key, data, prefix=StoragePrefix(source),
            content_type=content_type,
        )

        asset = Asset(
            type="audio",
            source=source,
            uri=uri,
            hash=content_hash,
            width=None,
            height=None,
            thumbnail=None,
            tags=tags or [],
            parent_id=parent_id,
            group_id=group_id,
            provenance=provenance,
            duration=None,
            mime_type=content_type,
        )
        await self.db.create_asset(asset)
        return asset
