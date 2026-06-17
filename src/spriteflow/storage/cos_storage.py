"""腾讯云 COS 存储适配器"""

from __future__ import annotations

import io
from typing import BinaryIO

from qcloud_cos import CosConfig, CosS3Client

from .base import StorageBackend, StoragePrefix
from ..config import settings


class COSStorage(StorageBackend):
    """腾讯云 COS 对象存储适配器

    Bucket: spriteflow-1258748206
    Region: ap-guangzhou
    路径前缀: uploaded/ generated/ derived/ thumbnails/ exports/
    """

    def __init__(
        self,
        secret_id: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
    ) -> None:
        cos = settings.cos
        self._secret_id = secret_id or cos.secret_id
        self._secret_key = secret_key or cos.secret_key
        self._bucket = bucket or cos.bucket
        self._region = region or cos.region

        config = CosConfig(
            Region=self._region,
            SecretId=self._secret_id,
            SecretKey=self._secret_key,
            Scheme="https",
        )
        self._client = CosS3Client(config)

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def region(self) -> str:
        return self._region

    @property
    def base_url(self) -> str:
        return f"https://{self._bucket}.cos.{self._region}.myqcloud.com"

    def build_uri(self, prefix: StoragePrefix, filename: str) -> str:
        """构建 COS URI: cos://bucket/prefix/filename"""
        key = self.build_key(prefix, filename)
        return f"cos://{self._bucket}/{key}"

    def _uri_to_key(self, uri: str) -> str:
        """URI 转 COS key"""
        if uri.startswith(f"cos://{self._bucket}/"):
            return uri[len(f"cos://{self._bucket}/"):]
        if uri.startswith(self.base_url + "/"):
            return uri[len(self.base_url + "/"):]
        # 已经是 key
        return uri

    async def upload(
        self,
        key: str,
        data: BinaryIO | bytes,
        prefix: StoragePrefix = StoragePrefix.UPLOADED,
        content_type: str = "image/png",
    ) -> str:
        """上传文件到 COS"""
        full_key = self.build_key(prefix, key)

        if isinstance(data, bytes):
            stream = io.BytesIO(data)
        else:
            stream = data

        self._client.put_object(
            Bucket=self._bucket,
            Key=full_key,
            Body=stream,
            ContentType=content_type,
        )

        uri = f"cos://{self._bucket}/{full_key}"
        return uri

    async def download(self, uri: str) -> bytes:
        """从 COS 下载文件"""
        key = self._uri_to_key(uri)
        response = self._client.get_object(
            Bucket=self._bucket,
            Key=key,
        )
        body = response["Body"]
        # StreamBody 需要 read() 而不是 getvalue()
        if hasattr(body, "read"):
            return body.read()
        if hasattr(body, "getvalue"):
            return body.getvalue()
        return bytes(body)

    async def delete(self, uri: str) -> bool:
        """从 COS 删除文件"""
        key = self._uri_to_key(uri)
        self._client.delete_object(
            Bucket=self._bucket,
            Key=key,
        )
        return True

    async def get_presigned_url(self, uri: str, expires: int = 3600) -> str:
        """获取 COS 公开访问 URL。

        桶已配置为公有读，直接构造 https://bucket.cos.region.myqcloud.com/key 即可，
        无需预签名，不暴露 SecretId，也不会过期。
        （expires 参数保留以兼容接口，实际不再使用）
        """
        key = self._uri_to_key(uri)
        return f"{self.base_url}/{key}"

    @staticmethod
    def get_public_url_from_http_url(http_url: str) -> str:
        """从已有的 HTTP COS URL（可能含查询参数/过期签名）还原为公开 URL。

        去掉查询参数即可。
        """
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(http_url)
        return urlunparse(parsed._replace(query=""))

    async def exists(self, uri: str) -> bool:
        """检查 COS 对象是否存在"""
        key = self._uri_to_key(uri)
        try:
            self._client.head_object(
                Bucket=self._bucket,
                Key=key,
            )
            return True
        except Exception:
            return False
