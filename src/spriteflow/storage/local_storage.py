"""本地文件系统存储 fallback（开发/测试用）"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from .base import StorageBackend, StoragePrefix


class LocalStorage(StorageBackend):
    """本地文件系统存储，目录结构与 COS 路径前缀对齐

    适用于开发/测试场景，无需 COS 凭证。
    """

    def __init__(self, base_dir: Path | str = "data/storage") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def build_uri(self, prefix: StoragePrefix, filename: str) -> str:
        """构建本地 URI: local://prefix/filename"""
        return f"local://{self.build_key(prefix, filename)}"

    def _uri_to_path(self, uri: str) -> Path:
        """URI 转本地路径"""
        if uri.startswith("local://"):
            relative = uri[len("local://"):]
            return self.base_dir / relative
        if uri.startswith(str(self.base_dir)):
            return Path(uri)
        return self.base_dir / uri

    async def upload(
        self,
        key: str,
        data: BinaryIO | bytes,
        prefix: StoragePrefix = StoragePrefix.UPLOADED,
        content_type: str = "image/png",
    ) -> str:
        """写入本地文件"""
        full_key = self.build_key(prefix, key)
        file_path = self.base_dir / full_key
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, bytes):
            file_path.write_bytes(data)
        else:
            file_path.write_bytes(data.read())

        return f"local://{full_key}"

    async def download(self, uri: str) -> bytes:
        """读取本地文件"""
        path = self._uri_to_path(uri)
        return path.read_bytes()

    async def delete(self, uri: str) -> bool:
        """删除本地文件"""
        path = self._uri_to_path(uri)
        if path.exists():
            path.unlink()
            return True
        return False

    async def get_presigned_url(self, uri: str, expires: int = 3600) -> str:
        """本地存储返回文件路径"""
        path = self._uri_to_path(uri)
        return str(path)

    async def exists(self, uri: str) -> bool:
        """检查本地文件是否存在"""
        return self._uri_to_path(uri).exists()
