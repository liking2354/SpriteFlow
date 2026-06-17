"""SQLAlchemy ORM 模型 — 通道、模型路由"""

import uuid
from sqlalchemy import Column, String, Text, Integer, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


def gen_uuid():
    return str(uuid.uuid4())


class Channel(Base):
    """通道（Provider 后端）配置"""
    __tablename__ = "model_channels"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200), nullable=False)
    provider_type = Column(String(50), nullable=False, index=True)
    base_url = Column(String(512), default="")
    api_key = Column(Text, default="")
    default_model = Column(String(200), default="")
    status = Column(String(20), default="active")  # active / inactive / error
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ModelRoute(Base):
    """模型 → 通道 路由映射"""
    __tablename__ = "model_routes"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    model_id = Column(String(200), nullable=False, index=True)
    channel_id = Column(String(36), nullable=False, index=True)
    priority = Column(Integer, default=0)  # 越小优先级越高
    model_override = Column(String(200), default="")  # 通道上的模型名覆盖
    param_overrides = Column(JSON, default=dict)  # 参数覆盖
    status = Column(String(20), default="active")  # active / inactive
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ModelDefault(Base):
    """每个分类（及子分类）的默认模型 — category + subcategory 联合主键"""
    __tablename__ = "model_defaults"

    category = Column(String(50), primary_key=True)
    subcategory = Column(String(50), primary_key=True, default="")
    model_id = Column(String(200), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
