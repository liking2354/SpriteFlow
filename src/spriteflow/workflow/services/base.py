"""
AI 服务抽象基类
"""
from abc import ABC, abstractmethod
from typing import Any


class AIServiceBase(ABC):
    """所有 AI 服务必须实现此接口"""

    @abstractmethod
    async def generate(self, input_params: dict, **kwargs: Any) -> dict:
        """
        执行 AI 生成任务

        Returns:
            {"outputs": [{"type": "text|image_url|video_url|audio_url", "value": "..."}]}
        """
        pass

    @abstractmethod
    def get_input_schema(self) -> dict:
        """返回此模型需要的输入参数 schema"""
        pass

    def supports_model(self, model_id: str) -> bool:
        return False
