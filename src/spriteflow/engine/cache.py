"""内容寻址缓存 — 相同输入跳过计算，直接返回缓存结果"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image

from ..config import settings


def _stable_hash(data: Any) -> str:
    """生成稳定的哈希值（确定性序列化）"""
    serialized = json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def compute_cache_key(
    node_type: str,
    params: dict[str, Any],
    input_hashes: dict[str, str],
) -> str:
    """计算节点输出的缓存 key

    缓存 key = hash(节点类型 + 参数 + 所有上游输入的 hash)
    """
    cache_data = {
        "node_type": node_type,
        "params": params,
        "inputs": input_hashes,
    }
    return _stable_hash(cache_data)


class CacheManager:
    """本地文件缓存管理器

    缓存目录: .cache/<cache_key>.png
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or settings.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_path(self, cache_key: str, ext: str = "png") -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{cache_key}.{ext}"

    def exists(self, cache_key: str, ext: str = "png") -> bool:
        """检查缓存是否存在"""
        return self.get_cache_path(cache_key, ext).exists()

    def load_image(self, cache_key: str) -> Image.Image | None:
        """从缓存加载图片"""
        path = self.get_cache_path(cache_key)
        if not path.exists():
            return None
        return Image.open(path).copy()

    def save_image(self, cache_key: str, image: Image.Image) -> Path:
        """保存图片到缓存"""
        path = self.get_cache_path(cache_key)
        image.save(path)
        return path

    def load_bytes(self, cache_key: str, ext: str = "png") -> bytes | None:
        """从缓存加载原始字节"""
        path = self.get_cache_path(cache_key, ext)
        if not path.exists():
            return None
        return path.read_bytes()

    def save_bytes(self, cache_key: str, data: bytes, ext: str = "png") -> Path:
        """保存原始字节到缓存"""
        path = self.get_cache_path(cache_key, ext)
        path.write_bytes(data)
        return path

    def clear(self) -> None:
        """清空缓存"""
        for f in self.cache_dir.iterdir():
            if f.is_file():
                f.unlink()

    def compute_input_hash(self, value: Any) -> str:
        """为输入值计算内容哈希"""
        if isinstance(value, Image.Image):
            # PIL.Image 哈希：用像素数据
            import io
            buf = io.BytesIO()
            value.save(buf, format="PNG")
            return hashlib.sha256(buf.getvalue()).hexdigest()[:16]
        elif isinstance(value, list):
            # IMAGE_BATCH 等列表
            hashes = [self.compute_input_hash(v) for v in value]
            return _stable_hash(hashes)
        elif isinstance(value, str | int | float | bool):
            return _stable_hash(value)
        elif isinstance(value, dict):
            return _stable_hash(value)
        else:
            return _stable_hash(str(value))
