"""
Replicate API 服务 — 图像 & 视频生成
"""
import asyncio
import logging
from ...config import settings
from .base import AIServiceBase

logger = logging.getLogger(__name__)

REPLICATE_MODEL_MAP = {
    "flux-schnell": "black-forest-labs/flux-schnell",
    "flux-2-dev": "black-forest-labs/flux-dev",
    "flux-2-pro": "black-forest-labs/flux-pro",
    "flux-1.1-pro": "black-forest-labs/flux-1.1-pro",
    "flux-1.1-pro-ultra": "black-forest-labs/flux-1.1-pro-ultra",
    "flux-dev": "black-forest-labs/flux-dev",
    "flux-pro": "black-forest-labs/flux-pro",
    "flux-2-flex": "black-forest-labs/flux-dev",
    "flux-2-dev-edit": "black-forest-labs/flux-dev",
    "flux-2-flex-edit": "black-forest-labs/flux-dev",
    "flux-2-pro-edit": "black-forest-labs/flux-dev",
    "sd-turbo-ultra": "stability-ai/sdxl",
    "sd-core-ultra": "stability-ai/sdxl",
    "wan-2.1": "wavespeedai/wan-2.1-i2v",
    "wan-2.2": "wavespeedai/wan-2.2-i2v",
    "wan2.5-text-to-image": "wavespeedai/wan-2.5-t2i",
    "wan2.5-image-edit": "wavespeedai/wan-2.5-edit",
    "wan2.5-image-to-video": "wavespeedai/wan-2.5-i2v",
    "wan2.5-image-to-video-fast": "wavespeedai/wan-2.5-i2v",
    "wan2.5-text-to-video": "wavespeedai/wan-2.5-t2v",
    "wan2.5-text-to-video-fast": "wavespeedai/wan-2.5-t2v",
    "wan2.6-text-to-image": "wavespeedai/wan-2.6-t2i",
    "wan2.6-image-to-video": "wavespeedai/wan-2.6-i2v",
    "wan2.6-text-to-video": "wavespeedai/wan-2.6-t2v",
    "wan2.2-text-to-video": "wavespeedai/wan-2.2-t2v",
    "wan2.2-image-to-video": "wavespeedai/wan-2.2-i2v",
    "wan2.2-5b-fast-t2v": "wavespeedai/wan-2.2-5b-fast-t2v",
    "wan2.2-animate": "wavespeedai/wan-2.2-animate",
    "wan2.2-edit-video": "wavespeedai/wan-2.2-edit-video",
    "wan2.2-spicy-image-to-video": "wavespeedai/wan-2.2-spicy-i2v",
    "wan2.2-spicy-video-extend": "wavespeedai/wan-2.2-spicy-video-extend",
    "bytedance-seedream-v4": "wavespeedai/seedream-v4",
    "bytedance-seedream-v4.5": "wavespeedai/seedream-v4.5",
    "bytedance-seedream-edit-v4": "wavespeedai/seedream-v4",
    "bytedance-seedream-v4.5-edit": "wavespeedai/seedream-v4.5",
    "seedance-lite-i2v": "wavespeedai/seedance-lite-i2v",
    "seedance-lite-t2v": "wavespeedai/seedance-lite-t2v",
    "seedance-pro-t2v": "wavespeedai/seedance-pro-t2v",
    "seedance-pro-i2v": "wavespeedai/seedance-pro-i2v",
    "seedance-pro-t2v-fast": "wavespeedai/seedance-pro-t2v-fast",
    "seedance-pro-i2v-fast": "wavespeedai/seedance-pro-i2v-fast",
    "seedance-v1.5-pro-i2v": "wavespeedai/seedance-v1.5-pro-i2v",
    "seedance-v1.5-pro-t2v": "wavespeedai/seedance-v1.5-pro-t2v",
    "seedance-v1.5-pro-i2v-fast": "wavespeedai/seedance-v1.5-pro-i2v-fast",
    "seedance-v1.5-pro-t2v-fast": "wavespeedai/seedance-v1.5-pro-t2v-fast",
    "seedance-v1.5-pro-video-extend": "wavespeedai/seedance-v1.5-pro-video-extend",
    "seedance-v1.5-pro-video-extend-fast": "wavespeedai/seedance-v1.5-pro-video-extend-fast",
    "nano-banana": "wavespeedai/nano-banana",
    "nano-banana-edit": "wavespeedai/nano-banana",
    "nano-banana-pro": "wavespeedai/nano-banana",
    "nano-banana-pro-edit": "wavespeedai/nano-banana",
    "wan2.6-image-edit": "wavespeedai/wan-2.6-edit",
    "qwen-image": "wavespeedai/qwen-image",
    "qwen-image-edit": "wavespeedai/qwen-image-edit",
    "qwen-image-edit-2511": "wavespeedai/qwen-image-edit",
    "qwen-image-edit-plus": "wavespeedai/qwen-image-edit",
    "qwen-image-edit-plus-lora": "wavespeedai/qwen-image-edit",
    "z-image-turbo": "wavespeedai/z-image-turbo",
    "chroma-image": "wavespeedai/chroma-image",
    "kling-o1-text-to-image": "wavespeedai/kling-o1-t2i",
    "kling-o1-edit-image": "wavespeedai/kling-o1-edit",
    "grok-imagine-text-to-image": "wavespeedai/grok-imagine",
    "hunyuan-image-2.1": "wavespeedai/hunyuan-image-2.1",
    "hunyuan-image-3.0": "wavespeedai/hunyuan-image-3.0",
    "google-imagen4": "wavespeedai/imagen4",
    "google-imagen4-fast": "wavespeedai/imagen4",
    "google-imagen4-ultra": "wavespeedai/imagen4",
    "midjourney-v7-text-to-image": "wavespeedai/midjourney-v7",
    "midjourney-v7-image-to-image": "wavespeedai/midjourney-v7",
    "midjourney-v7-omni-reference": "wavespeedai/midjourney-v7",
    "midjourney-v7-style-reference": "wavespeedai/midjourney-v7",
    "vidu-q2-text-to-image": "wavespeedai/vidu-q2",
    "vidu-q2-reference-to-image": "wavespeedai/vidu-q2",
    "veo3.1-image-to-video": "wavespeedai/veo3.1-i2v",
    "veo3.1-text-to-video": "wavespeedai/veo3.1-t2v",
    "veo3.1-fast-image-to-video": "wavespeedai/veo3.1-i2v",
    "veo3.1-fast-text-to-video": "wavespeedai/veo3.1-t2v",
    "openai-sora": "wavespeedai/sora",
    "openai-sora-2-text-to-video": "wavespeedai/sora-2-t2v",
    "openai-sora-2-image-to-video": "wavespeedai/sora-2-i2v",
    "openai-sora-2-pro-text-to-video": "wavespeedai/sora-2-pro-t2v",
    "openai-sora-2-pro-image-to-video": "wavespeedai/sora-2-pro-i2v",
    "kling-v2.5-turbo-pro-t2v": "wavespeedai/kling-v2.5-turbo-pro-t2v",
    "kling-v2.5-turbo-pro-i2v": "wavespeedai/kling-v2.5-turbo-pro-i2v",
    "kling-v2.5-turbo-std-i2v": "wavespeedai/kling-v2.5-turbo-std-i2v",
    "kling-v2.6-pro-t2v": "wavespeedai/kling-v2.6-pro-t2v",
    "kling-v2.6-pro-i2v": "wavespeedai/kling-v2.6-pro-i2v",
    "kling-v2.6-pro-motion-control": "wavespeedai/kling-v2.6-pro-motion-control",
    "kling-o1-text-to-video": "wavespeedai/kling-o1-t2v",
    "kling-o1-image-to-video": "wavespeedai/kling-o1-i2v",
    "kling-o1-video-edit": "wavespeedai/kling-o1-edit",
    "kling-o1-video-edit-fast": "wavespeedai/kling-o1-edit",
    "kling-o1-reference-to-video": "wavespeedai/kling-o1-ref",
    "kling-o1-standard-image-to-video": "wavespeedai/kling-o1-std-i2v",
    "kling-o1-standard-reference-to-video": "wavespeedai/kling-o1-std-ref",
    "kling-o1-standard-video-edit": "wavespeedai/kling-o1-std-edit",
    "grok-imagine-text-to-video": "wavespeedai/grok-imagine-t2v",
    "grok-imagine-image-to-video": "wavespeedai/grok-imagine-i2v",
    "hunyuan-text-to-video": "wavespeedai/hunyuan-t2v",
    "hunyuan-fast-text-to-video": "wavespeedai/hunyuan-t2v",
    "hunyuan-image-to-video": "wavespeedai/hunyuan-i2v",
    "midjourney-v7-image-to-video": "wavespeedai/midjourney-v7",
    "vidu-q2-turbo-start-end-video": "wavespeedai/vidu-q2",
    "vidu-q2-pro-start-end-video": "wavespeedai/vidu-q2",
    "vidu-q2-reference": "wavespeedai/vidu-q2",
    "luma-modify-video": "wavespeedai/luma-modify",
    "luma-flash-reframe": "wavespeedai/luma-flash-reframe",
}


class ReplicateService(AIServiceBase):

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import replicate
                self._client = replicate.Client(api_token=settings.replicate_api_token)
            except ImportError:
                raise RuntimeError("replicate package not installed. Run: pip install replicate")
        return self._client

    def supports_model(self, model_id: str) -> bool:
        return model_id.lower() in REPLICATE_MODEL_MAP

    async def generate(self, input_params: dict, **kwargs) -> dict:
        model_id = kwargs.get("model", "")
        replicate_model = REPLICATE_MODEL_MAP.get(model_id.lower())
        if not replicate_model:
            raise ValueError(f"Unsupported replicate model: {model_id}")

        client = self._get_client()
        replicate_input = {}

        prompt = input_params.get("prompt", "")
        if prompt:
            replicate_input["prompt"] = prompt

        image_url = input_params.get("image_url") or input_params.get("image")
        if image_url:
            replicate_input["image"] = image_url
        if input_params.get("last_frame"):
            replicate_input["last_frame"] = input_params.get("last_frame")

        for key in ("width", "height", "num_outputs", "num_inference_steps",
                     "guidance_scale", "aspect_ratio", "duration", "resolution",
                     "fps", "negative_prompt", "seed"):
            if key in input_params and input_params[key] is not None:
                replicate_input[key] = input_params[key]

        if not replicate_input:
            replicate_input["prompt"] = "a beautiful scene"

        try:
            prediction = await asyncio.to_thread(
                client.run, replicate_model, input=replicate_input)

            output_value = prediction
            if isinstance(prediction, list) and len(prediction) > 0:
                output_value = prediction[0]

            if isinstance(output_value, str):
                if output_value.endswith((".mp4", ".webm", ".mov")):
                    return {"outputs": [{"type": "video_url", "value": output_value}]}
                return {"outputs": [{"type": "image_url", "value": output_value}]}
            elif hasattr(prediction, "url"):
                return {"outputs": [{"type": "image_url", "value": prediction.url}]}
            else:
                return {"outputs": [{"type": "text", "value": str(output_value)}]}
        except Exception as e:
            logger.error(f"Replicate API error for model {model_id}: {e}")
            raise

    def get_input_schema(self) -> dict:
        return {
            "properties": {
                "prompt": {"type": "string", "title": "Prompt", "description": "Text prompt describing the desired output"},
                "image_url": {"type": "string", "title": "Image URL", "description": "URL of input image (for img2img/img2video)"},
                "width": {"type": "integer", "title": "Width", "default": 1024},
                "height": {"type": "integer", "title": "Height", "default": 1024},
                "num_outputs": {"type": "integer", "title": "Number of Outputs", "default": 1},
                "seed": {"type": "integer", "title": "Seed", "description": "Random seed for reproducibility"},
                "negative_prompt": {"type": "string", "title": "Negative Prompt", "description": "Things to avoid in the output"},
            },
            "required": ["prompt"]
        }
