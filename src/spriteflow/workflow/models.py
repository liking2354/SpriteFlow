"""
SQLAlchemy ORM 模型 — 工作流、运行历史、AI 提供商配置
"""
import datetime
import uuid
from sqlalchemy import Column, String, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


def gen_uuid():
    return str(uuid.uuid4())


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), default="Untitled", nullable=False)
    data = Column(JSON, default=dict, nullable=False)
    edges = Column(JSON, default=list, nullable=False)
    category = Column(String(100), default="General")
    thumbnail = Column(Text, nullable=True)
    is_published = Column(Boolean, default=False, nullable=False)
    is_vadoo = Column(String(10), default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RunHistory(Base):
    __tablename__ = "workflow_run_history"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    workflow_id = Column(String(36), default="")
    node_id = Column(String(100), default="")
    run_id = Column(String(36), default=gen_uuid, index=True)
    node_run_id = Column(String(36), default=gen_uuid)
    status = Column(String(50), default="pending")
    node_data = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ModelSettings(Base):
    __tablename__ = "workflow_model_settings"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    provider = Column(String(50), unique=True, nullable=False, index=True)
    api_key = Column(String(512), default="")
    base_url = Column(String(512), default="")
    is_enabled = Column(String(10), default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ModelConfig(Base):
    __tablename__ = "workflow_model_configs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    model_id = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    is_visible = Column(String(10), default="true")
    is_deleted = Column(String(10), default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CustomNodeSchema(Base):
    __tablename__ = "workflow_custom_node_schemas"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    model_id = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    service = Column(String(50), nullable=False)
    input_schema = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkflowPreset(Base):
    """工作流预设模板 — 持久化存储预设工作流，支持可视化编辑"""
    __tablename__ = "workflow_presets"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    preset_id = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    icon = Column(String(50), default="plus")
    image = Column(Text, default="")
    category = Column(String(100), default="General")
    nodes = Column(JSON, default=list, nullable=False)
    edges = Column(JSON, default=list, nullable=False)
    sort_order = Column(String(10), default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
