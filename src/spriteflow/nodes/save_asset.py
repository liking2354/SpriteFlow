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

    输入: image / audio / text
    输出: asset_id
    """

    INPUTS: dict[str, PortType] = {
        "image": PortType.IMAGE,
        "audio": PortType.AUDIO,
        "text": PortType.STRING,
    }
    OUTPUTS: dict[str, PortType] = {"asset_id": PortType.STRING}
    CATEGORY = "export"
    _node_type = "SaveAsset"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        """保存素材到 COS 并写入数据库

        根据输入类型自动选择存储策略：
        - image → PNG 编码 + 缩略图
        - audio → 直接上传，type=audio
        - text → UTF-8 编码上传，type=text
        """
        if ctx.storage is None:
            raise ValueError("SaveAsset 需要 storage 后端")

        source = params.get("source", "generated")
        prefix = StoragePrefix(source)
        content_hash = ""
        uri = ""
        thumbnail_uri = None
        asset_type = "image"
        asset_width = None
        asset_height = None
        asset_text_preview = None
        asset_mime_type = None

        # ── 图片输入 ──
        image = inputs.get("image")
        if image is not None:
            buf = io.BytesIO()
            if not isinstance(image, Image.Image):
                raise ValueError(f"image 必须是 PIL.Image，实际类型: {type(image)}")
            image.save(buf, format="PNG")
            data = buf.getvalue()
            content_hash = hashlib.sha256(data).hexdigest()[:32]

            file_key = f"{content_hash}.png"
            uri = await ctx.storage.upload(file_key, data, prefix=prefix)

            thumb = image.copy()
            thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)
            thumb_buf = io.BytesIO()
            thumb.save(thumb_buf, format="PNG")
            thumb_data = thumb_buf.getvalue()
            thumb_key = f"{content_hash}.png"
            thumbnail_uri = await ctx.storage.upload(
                thumb_key, thumb_data, prefix=StoragePrefix.THUMBNAILS
            )
            asset_type = "image"
            asset_width = image.width
            asset_height = image.height
            asset_mime_type = "image/png"

        # ── 音频输入 ──
        elif inputs.get("audio") is not None:
            audio_input = inputs["audio"]
            if isinstance(audio_input, bytes):
                data = audio_input
            elif isinstance(audio_input, str):
                data = audio_input.encode("utf-8")
            else:
                raise ValueError(f"audio 输入类型不支持: {type(audio_input)}")

            content_hash = hashlib.sha256(data).hexdigest()[:32]
            ext = params.get("audio_ext", "mp3")
            content_type = params.get("audio_mime", "audio/mpeg")
            file_key = f"{content_hash}.{ext}"
            uri = await ctx.storage.upload(file_key, data, prefix=prefix, content_type=content_type)
            asset_type = "audio"
            asset_mime_type = content_type

        # ── 文本输入 ──
        elif inputs.get("text") is not None:
            text_content = str(inputs["text"])
            data = text_content.encode("utf-8")
            content_hash = hashlib.sha256(data).hexdigest()[:32]

            file_key = f"{content_hash}.txt"
            uri = await ctx.storage.upload(
                file_key, data, prefix=prefix,
                content_type="text/plain; charset=utf-8",
            )
            asset_type = "text"
            asset_text_preview = text_content[:200] if len(text_content) > 200 else text_content
            asset_mime_type = "text/plain"

        else:
            raise ValueError("SaveAsset 需要 image、audio 或 text 输入中的至少一个")

        # 写入数据库
        asset_id = ""
        if hasattr(ctx, 'db') and ctx.db is not None:
            asset = Asset(
                type=asset_type,
                source=source,
                uri=uri,
                hash=content_hash,
                width=asset_width,
                height=asset_height,
                thumbnail=thumbnail_uri,
                tags=params.get("tags", []),
                parent_id=params.get("parent_id"),
                text_preview=asset_text_preview,
                mime_type=asset_mime_type,
            )
            await ctx.db.create_asset(asset)
            asset_id = asset.id

        ctx.log(f"素材已保存: {uri}")
        return {"asset_id": asset_id or content_hash}
