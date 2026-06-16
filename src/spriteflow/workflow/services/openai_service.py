"""
OpenAI 兼容 API 服务 — 支持所有兼容 OpenAI 接口的服务
"""
import logging
from openai import AsyncOpenAI
from ...config import settings
from .base import AIServiceBase

logger = logging.getLogger(__name__)


class OpenAICompatibleService(AIServiceBase):

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key or "sk-placeholder",
            base_url=settings.openai_base_url,
        )

    def supports_model(self, model_id: str) -> bool:
        prefixes = (
            "gpt-", "gpt5", "o1", "o3", "o4",
            "openai-", "dall-e", "claude-", "gemini-",
            "deepseek-", "llama-", "qwen-",
        )
        return any(model_id.lower().startswith(p) for p in prefixes)

    async def generate(self, input_params: dict, **kwargs) -> dict:
        model = kwargs.get("model", "gpt-4o")
        prompt = input_params.get("prompt", "")
        system_prompt = input_params.get("system_prompt", "")
        image_url = input_params.get("image_url", "")
        image_urls = input_params.get("image_urls", [])
        if isinstance(image_urls, str):
            image_urls = [image_urls]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        content = []
        if prompt:
            content.append({"type": "text", "text": prompt})

        images_to_send = [image_url] if image_url else []
        images_to_send.extend(image_urls)
        for img in images_to_send:
            if img and (img.startswith("data:") or img.startswith("http")):
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img, "detail": "auto"}
                })

        if not content:
            content = [{"type": "text", "text": prompt or "Generate content"}]
        messages.append({"role": "user", "content": content})

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=input_params.get("temperature", 0.7),
                max_tokens=input_params.get("max_tokens", 4096),
            )
            text = response.choices[0].message.content or ""
            return {"outputs": [{"type": "text", "value": text}]}
        except Exception as e:
            logger.error(f"OpenAI API error for model {model}: {e}")
            raise

    def get_input_schema(self) -> dict:
        return {
            "properties": {
                "prompt": {"type": "string", "title": "Prompt", "description": "The text prompt for generation"},
                "system_prompt": {"type": "string", "title": "System Prompt", "description": "System instructions for the AI"},
                "image_url": {"type": "string", "title": "Image URL", "description": "URL of input image (for vision models)"},
                "temperature": {"type": "number", "title": "Temperature", "default": 0.7, "minimum": 0, "maximum": 2},
                "max_tokens": {"type": "integer", "title": "Max Tokens", "default": 4096},
            },
            "required": ["prompt"]
        }
