"""LoadAsset 节点 — 从 COS/本地存储加载素材到内存"""

from __future__ import annotations

import io

from PIL import Image

from ..engine.node import Node
from ..engine.types import PortType


class LoadAssetNode(Node):
    """加载素材节点

    输入: asset_id (参数)
    输出: image
    """

    INPUTS: dict[str, PortType] = {}
    OUTPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    CATEGORY = "load"
    _node_type = "LoadAsset"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        """从存储加载素材"""
        asset_id = params.get("asset_id", "")
        if not asset_id:
            raise ValueError("LoadAsset 需要 asset_id 参数")

        if ctx.storage is None:
            raise ValueError("LoadAsset 需要 storage 后端")

        # 查询数据库获取 URI
        if hasattr(ctx, 'db') and ctx.db is not None:
            asset = await ctx.db.get_asset(asset_id)
            if asset:
                data = await ctx.storage.download(asset.uri)
                image = Image.open(io.BytesIO(data)).convert("RGBA")
                ctx.log(f"加载素材: {asset_id}")
                return {"image": image}

        # 尝试直接用 asset_id 作为 URI 下载
        data = await ctx.storage.download(asset_id)
        image = Image.open(io.BytesIO(data)).convert("RGBA")
        ctx.log(f"加载素材: {asset_id}")
        return {"image": image}
