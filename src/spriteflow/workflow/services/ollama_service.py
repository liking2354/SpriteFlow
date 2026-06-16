"""
Ollama 本地 LLM 服务
"""
import base64
import logging
import httpx
from ...config import settings
from .base import AIServiceBase

logger = logging.getLogger(__name__)


class OllamaService(AIServiceBase):

    def __init__(self):
        self.base_url = settings.ollama_host.rstrip("/")

    def supports_model(self, model_id: str) -> bool:
        prefixes = (
            "llama-", "mistral", "gemma", "phi", "qwen",
            "deepseek", "codellama", "mixtral", "command-r",
            "yi-", "falcon", "dbrx", "wizardlm", "solar",
            "orca", "vicuna", "alpaca",
        )
        return any(model_id.lower().startswith(p) for p in prefixes)

    async def generate(self, input_params: dict, **kwargs) -> dict:
        model = kwargs.get("model", "llama3")
        prompt = input_params.get("prompt", "")
        system_prompt = input_params.get("system_prompt", "")

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": input_params.get("temperature", 0.7)}
        }
        if system_prompt:
            payload["system"] = system_prompt

        image_url = input_params.get("image_url", "")
        images = []
        if image_url:
            if image_url.startswith("data:"):
                images.append(image_url)
            else:
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(image_url, timeout=30)
                        img_data = base64.b64encode(resp.content).decode()
                        images.append(f"data:{resp.headers.get('content-type', 'image/png')};base64,{img_data}")
                except Exception as e:
                    logger.warning(f"Failed to fetch image for Ollama: {e}")
        if images:
            payload["images"] = images

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
            return {"outputs": [{"type": "text", "value": data.get("response", "")}]}
        except httpx.ConnectError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}. Make sure Ollama is running.")
        except Exception as e:
            logger.error(f"Ollama API error for model {model}: {e}")
            raise

    def get_input_schema(self) -> dict:
        return {
            "properties": {
                "prompt": {"type": "string", "title": "Prompt", "description": "The text prompt for generation"},
                "system_prompt": {"type": "string", "title": "System Prompt", "description": "System instructions for the model"},
                "temperature": {"type": "number", "title": "Temperature", "default": 0.7, "minimum": 0, "maximum": 2}
            },
            "required": ["prompt"]
        }
