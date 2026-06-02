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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def cos(self) -> COSSettings:
        return COSSettings()

    def ensure_dirs(self) -> None:
        """确保必要目录存在"""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


settings = AppSettings()
