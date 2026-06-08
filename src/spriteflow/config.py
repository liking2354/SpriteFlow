"""SpriteFlow 全局配置 — Pydantic BaseSettings 自动读取环境变量 / .env 文件"""

from pathlib import Path

from pydantic_settings import BaseSettings


class COSSettings(BaseSettings):
    """腾讯云 COS 对象存储配置"""

    secret_id: str = ""
    secret_key: str = ""
    bucket: str = "spriteflow-1258748206"
    region: str = "ap-guangzhou"

    model_config = {"env_prefix": "COS_"}


class AppSettings(BaseSettings):
    """应用全局配置"""

    # 本地路径
    project_root: Path = Path(__file__).resolve().parent.parent.parent
    database_path: Path = Path("data/assets.db")
    cache_dir: Path = Path(".cache")

    # 路由配置
    routing_config: Path = project_root / "config" / "routing.yaml"

    # 火山方舟 Seedream
    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    seedream_model: str = "doubao-seedream-5-0-260128"
    # 火山方舟 Seedance（视频生成，复用 ark_api_key 与 base_url）
    seedance_model: str = "doubao-seedance-1-5-pro-251215"
    seedance_poll_interval_sec: float = 5.0
    seedance_request_timeout: float = 60.0

    # OpenRouter 多模型统一入口
    openrouter_api_key: str = ""
    openrouter_default_model: str = "openai/gpt-image-1"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # 生成任务重试
    generation_retry_count: int = 2
    generation_retry_delay_sec: float = 1.0

    # 图片下载超时（秒）
    image_download_timeout: float = 120.0

    # 火山引擎 AI MediaKit（图像处理）
    volc_access_key_id: str = ""
    volc_secret_access_key: str = ""
    volc_mediakit_api_key: str = ""  # Bearer Token for slim-image / resize-image

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def cos(self) -> COSSettings:
        return COSSettings()

    def ensure_dirs(self) -> None:
        """确保必要目录存在"""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


settings = AppSettings()
