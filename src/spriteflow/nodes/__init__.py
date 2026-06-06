"""SpriteFlow 节点库 — 自动注册所有核心节点"""

from ..engine.node import register_node
from .load_asset import LoadAssetNode
from .text2img import Text2ImgNode
from .img2img import Img2ImgNode
from .multi_image_fusion import MultiImageFusionNode
from .sequential_images import SequentialImagesNode
from .remove_bg import RemoveBGNode
from .save_asset import SaveAssetNode
from .sprite_align import SpriteAlignNode
from .extract_frames import ExtractFramesNode
from .pack_spritesheet import PackSpritesheetNode

# 注册所有核心节点
register_node("LoadAsset", LoadAssetNode)
register_node("Text2Img", Text2ImgNode)
register_node("Img2Img", Img2ImgNode)
register_node("MultiImageFusion", MultiImageFusionNode)
register_node("SequentialImages", SequentialImagesNode)
register_node("RemoveBG", RemoveBGNode)
register_node("SpriteAlign", SpriteAlignNode)
register_node("ExtractFrames", ExtractFramesNode)
register_node("PackSpritesheet", PackSpritesheetNode)
register_node("SaveAsset", SaveAssetNode)

__all__ = [
    "LoadAssetNode",
    "Text2ImgNode",
    "Img2ImgNode",
    "MultiImageFusionNode",
    "SequentialImagesNode",
    "RemoveBGNode",
    "SpriteAlignNode",
    "ExtractFramesNode",
    "PackSpritesheetNode",
    "SaveAssetNode",
]
