"""SaveAsset 节点 — 保存素材到 COS + 写入元数据"""

from __future__ import annotations

import hashlib
import io

from PIL import Image

from ..engine.node import Node
from ..engine.types import PortType
from ..storage.base import StoragePrefix
from ..asset_hub.models import Asset


class SaveAssetNode(Node):
    """保存素材节点

    输入: image
    输出: asset_id
    """

    INPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    OUTPUTS: dict[str, PortType] = {"asset_id": PortType.STRING}
    CATEGORY = "export"
    _node_type = "SaveAsset"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        """保存图片到 COS 并写入数据库"""
        image = inputs.get("image")
        if image is None:
            raise ValueError("SaveAsset 需要 image 输入")

        if ctx.storage is None:
            raise ValueError("SaveAsset 需要 storage 后端")

        # 编码图片
        buf = io.BytesIO()
        if not isinstance(image, Image.Image):
            raise ValueError(f"image 必须是 PIL.Image，实际类型: {type(image)}")
        image.save(buf, format="PNG")
        data = buf.getvalue()

        # 计算内容哈希
        content_hash = hashlib.sha256(data).hexdigest()[:32]

        # 确定存储前缀
        source = params.get("source", "generated")
        prefix = StoragePrefix(source)

        # 上传到 COS
        file_key = f"{content_hash}.png"
        uri = await ctx.storage.upload(file_key, data, prefix=prefix)

        # 生成缩略图
        thumb = image.copy()
        thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)
        thumb_buf = io.BytesIO()
        thumb.save(thumb_buf, format="PNG")
        thumb_data = thumb_buf.getvalue()

        thumb_key = f"{content_hash}.png"
        thumbnail_uri = await ctx.storage.upload(
            thumb_key, thumb_data, prefix=StoragePrefix.THUMBNAILS
        )

        # 写入数据库
        asset_id = ""
        if hasattr(ctx, 'db') and ctx.db is not None:
            asset = Asset(
                type="image",
                source=source,
                uri=uri,
                hash=content_hash,
                width=image.width,
                height=image.height,
                thumbnail=thumbnail_uri,
                tags=params.get("tags", []),
                parent_id=params.get("parent_id"),
            )
            await ctx.db.create_asset(asset)
            asset_id = asset.id

        ctx.log(f"素材已保存: {uri}")
        return {"asset_id": asset_id or content_hash}
