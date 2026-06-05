"""火山方舟 Seedance 2.0 视频生成 Provider

封装 4 个异步任务 API：
  POST   /contents/generations/tasks            创建任务
  GET    /contents/generations/tasks/{id}       查询单任务
  GET    /contents/generations/tasks            列表（远端分页）
  DELETE /contents/generations/tasks/{id}       取消（仅 queued）/ 删除（其它结束态）

文档：
  https://www.volcengine.com/docs/82379/1520757
  https://www.volcengine.com/docs/82379/1521309
  https://www.volcengine.com/docs/82379/1521675
  https://www.volcengine.com/docs/82379/1521720

任务状态枚举：queued / running / succeeded / failed / cancelled / expired
注意：成功后 content.video_url 仅 24h 有效，必须立即下载落库。
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .base import Capability, Credential, Provider


class SeedanceProvider(Provider):
    name = "seedance"
    capabilities = {Capability.TEXT2VIDEO, Capability.IMG2VIDEO}

    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
    DEFAULT_MODEL = "doubao-seedance-2-0-260128"

    def __init__(
        self,
        api_key: str = "",
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self._model = model or self.DEFAULT_MODEL
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    # 适配 Provider.invoke：当前主要靠下方裸方法，这里让节点也能调用
    async def invoke(
        self,
        cap: Capability,
        payload: dict[str, Any],
        cred: Credential,
    ) -> dict[str, Any]:
        if cap not in self.capabilities:
            raise ValueError(f"Seedance 不支持能力 {cap}")
        api_key = cred.api_key or self._api_key
        return await self.create_task(payload, api_key=api_key)

    # ------------------------------- 4 个 API -------------------------------

    async def create_task(
        self,
        body: dict[str, Any],
        *,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """创建视频生成任务，返回 {"id": "..."}（含远端原始字段）"""
        url = f"{self._base_url}/contents/generations/tasks"
        async with httpx.AsyncClient(timeout=self._timeout) as cli:
            r = await cli.post(url, headers=self._headers(api_key), json=body)
            self._raise_for_status(r)
            return r.json()

    async def fetch_task(
        self,
        task_id: str,
        *,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """查询单任务详情"""
        url = f"{self._base_url}/contents/generations/tasks/{task_id}"
        async with httpx.AsyncClient(timeout=self._timeout) as cli:
            r = await cli.get(url, headers=self._headers(api_key))
            self._raise_for_status(r)
            return r.json()

    async def list_tasks(
        self,
        *,
        page_num: int = 1,
        page_size: int = 20,
        status: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """查询任务列表（远端分页）"""
        url = f"{self._base_url}/contents/generations/tasks"
        params: dict[str, Any] = {
            "page_num": page_num,
            "page_size": page_size,
        }
        if status:
            params["status"] = status
        if model:
            params["model"] = model
        async with httpx.AsyncClient(timeout=self._timeout) as cli:
            r = await cli.get(url, headers=self._headers(api_key), params=params)
            self._raise_for_status(r)
            return r.json()

    async def delete_task(
        self,
        task_id: str,
        *,
        api_key: str | None = None,
    ) -> bool:
        """取消（queued）或删除（其它结束态）任务

        Returns: True 若 2xx
        """
        url = f"{self._base_url}/contents/generations/tasks/{task_id}"
        async with httpx.AsyncClient(timeout=self._timeout) as cli:
            r = await cli.delete(url, headers=self._headers(api_key))
            # 已不存在或已结束 → 视作成功
            if r.status_code == 404:
                return True
            self._raise_for_status(r)
            return True

    # ------------------------------- 工具 -------------------------------

    @staticmethod
    async def download_video(url: str, *, retries: int = 3, timeout: float = 120.0) -> bytes:
        """从远端下载视频到内存（带重试）。"""
        last_err: Exception | None = None
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cli:
            for i in range(retries):
                try:
                    r = await cli.get(url)
                    r.raise_for_status()
                    return r.content
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    await asyncio.sleep(1.5 * (i + 1))
        raise RuntimeError(f"视频下载失败（{retries} 次重试）：{last_err}")

    def _headers(self, api_key: str | None) -> dict[str, str]:
        key = api_key or self._api_key
        if not key:
            raise RuntimeError("Seedance 未配置 ARK_API_KEY")
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_for_status(r: httpx.Response) -> None:
        if r.is_success:
            return
        try:
            payload = r.json()
        except Exception:  # noqa: BLE001
            payload = {"raw": r.text}
        # 火山方舟错误格式通常为 {"error":{"code":"...","message":"..."}} 或扁平字段
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            code = str(err.get("code", r.status_code))
            msg = err.get("message", r.text)
            # 已知错误友好化
            friendly = _friendly_error(code, str(msg))
            if friendly:
                raise RuntimeError(friendly)
            raise RuntimeError(f"Seedance API {r.status_code} {code}: {msg}")
        raise RuntimeError(f"Seedance API {r.status_code}: {payload}")


# 将常见错误码转成更友好的中文提示
_FRIENDLY_ERRORS = {
    "InputImageSensitiveContentDetected": (
        "输入图片被审核判定为含敏感信息。Seedance 不支持真人脸参考图，"
        "且对暴露/敏感内容审核较严，请改用 AI 生成的角色/物体/场景图，"
        "或先尝试纯文生视频验证链路。"
    ),
    "InputTextSensitiveContentDetected": (
        "提示词被审核判定为含敏感信息，请避免涉政/暴力/色情等内容。"
    ),
    "ModelNotOpen": (
        "当前模型未开通。请到火山方舟控制台 > 在线推理 开通对应模型，"
        "或在「高级参数」里切换到已开通的模型 ID（如 1.5 Pro）。"
    ),
    "InvalidParameter": "参数错误：请检查比例/分辨率/时长是否在模型支持范围内。",
    "RateLimitExceeded": "触发限流，请稍后重试。",
    "InsufficientQuota": "账号额度不足，请前往控制台充值或调整。",
}


def _friendly_error(code: str, msg: str) -> str | None:
    base = _FRIENDLY_ERRORS.get(code)
    if not base:
        return None
    return f"{base}\n（原始：{code}: {msg}）"
