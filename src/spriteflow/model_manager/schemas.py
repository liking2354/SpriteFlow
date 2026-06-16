"""Pydantic 请求/响应模型"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


# ---- 通道 ----

class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=200)
    provider_type: str = Field(..., min_length=1, max_length=50)
    base_url: str = Field(default="", max_length=512)
    api_key: str = Field(default="")
    default_model: str = Field(default="", max_length=200)
    metadata_: Optional[dict] = Field(default=None, alias="metadata")


class ChannelUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=200)
    base_url: Optional[str] = Field(default=None, max_length=512)
    api_key: Optional[str] = None
    default_model: Optional[str] = Field(default=None, max_length=200)
    status: Optional[str] = Field(default=None, pattern="^(active|inactive)$")
    metadata_: Optional[dict] = Field(default=None, alias="metadata")


class ChannelResponse(BaseModel):
    id: str
    name: str
    display_name: str
    provider_type: str
    base_url: str
    default_model: str
    status: str
    metadata_: Optional[dict] = Field(default=None, alias="metadata")
    route_count: int = 0
    created_at: str
    updated_at: str


class ChannelListResponse(BaseModel):
    items: list[ChannelResponse]
    total: int


class ChannelTestResult(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[float] = None


# ---- 模型路由 ----

class ModelRouteCreate(BaseModel):
    channel_id: str
    priority: int = 0
    model_override: str = Field(default="", max_length=200)
    param_overrides: dict = Field(default_factory=dict)
    status: str = Field(default="active", pattern="^(active|inactive)$")


class ModelRouteUpdate(BaseModel):
    priority: Optional[int] = None
    model_override: Optional[str] = Field(default=None, max_length=200)
    param_overrides: Optional[dict] = None
    status: Optional[str] = Field(default=None, pattern="^(active|inactive)$")


class RouteResponse(BaseModel):
    id: str
    model_id: str
    channel_id: str
    channel_name: str = ""
    channel_display_name: str = ""
    priority: int
    model_override: str
    param_overrides: dict
    status: str
    created_at: str
    updated_at: str


class ModelRoutesPayload(BaseModel):
    """批量设置某模型的所有路由"""
    routes: list[ModelRouteCreate]


class ModelWithRoutes(BaseModel):
    """模型及其路由配置"""
    model_id: str
    name: str = ""
    category: str = ""
    service: str = ""
    routes: list[RouteResponse] = []
    is_default: bool = False


class ModelListResponse(BaseModel):
    items: list[ModelWithRoutes]
    total: int
    offset: int = 0
    limit: int = 20


# ---- 模型注册表条目 ----

class RegistryModel(BaseModel):
    model_id: str
    name: str
    category: str
    service: str


class RegistryListResponse(BaseModel):
    items: list[RegistryModel]
    total: int


# ---- 默认模型 ----

class ModelDefaultUpdate(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=200)


class ModelDefaultEntry(BaseModel):
    category: str
    model_id: str


class ModelDefaultsResponse(BaseModel):
    defaults: dict[str, str]  # category → model_id 映射
