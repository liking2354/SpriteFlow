"""存储后端抽象接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import BinaryIO


class StoragePrefix(str, Enum):
    """COS 路径前缀，与设计文档目录结构对齐"""

    UPLOADED = "uploaded"
    GENERATED = "generated"
    DERIVED = "derived"
    THUMBNAILS = "thumbnails"
    EXPORTS = "exports"
    VIDEOS = "videos"
    AI_PROCESSED = "ai_processed"


class StorageBackend(ABC):
    """存储后端抽象接口

    所有存储实现（COS、本地文件系统）都遵循此接口。
    """

    @abstractmethod
    async def upload(
        self,
        key: str,
        data: BinaryIO | bytes,
        prefix: StoragePrefix = StoragePrefix.UPLOADED,
        content_type: str = "image/png",
    ) -> str:
        """上传文件，返回完整 URI

        Args:
            key: 文件名（如 hash.png）
            data: 文件数据
            prefix: 路径前缀
            content_type: MIME 类型

        Returns:
            完整的对象 URI
        """
        ...

    @abstractmethod
    async def download(self, uri: str) -> bytes:
        """下载文件，返回字节流"""
        ...

    @abstractmethod
    async def delete(self, uri: str) -> bool:
        """删除文件，返回是否成功"""
        ...

    @abstractmethod
    async def get_presigned_url(self, uri: str, expires: int = 3600) -> str:
        """获取预签名 URL（临时访问链接）"""
        ...

    @abstractmethod
    async def exists(self, uri: str) -> bool:
        """检查文件是否存在"""
        ...

    def build_key(self, prefix: StoragePrefix, filename: str) -> str:
        """构建对象 key：prefix/filename"""
        return f"{prefix.value}/{filename}"

    def build_uri(self, prefix: StoragePrefix, filename: str) -> str:
        """构建完整 URI（由子类实现具体协议头）"""
        key = self.build_key(prefix, filename)
        return key
