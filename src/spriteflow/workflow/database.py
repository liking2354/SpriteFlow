"""
SQLAlchemy 异步数据库引擎 — 工作流模块专用
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from ..config import settings

engine = create_async_engine(
    settings.workflow_db_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.workflow_db_url else {},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取工作流数据库会话"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化工作流数据库 — 创建所有表"""
    from .models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 为已有数据库添加新列（避免旧表缺失字段报错）
        try:
            await conn.run_sync(
                lambda sync_conn: sync_conn.exec_driver_sql(
                    "ALTER TABLE workflows ADD COLUMN is_published BOOLEAN DEFAULT 0 NOT NULL"
                )
            )
        except Exception:
            pass  # 列已存在则忽略
