"""
SQLAlchemy 异步数据库引擎 — 工作流模块专用
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event
from ..config import settings

engine = create_async_engine(
    settings.workflow_db_url,
    echo=False,
    connect_args={
        **({"check_same_thread": False, "timeout": 30} if "sqlite" in settings.workflow_db_url else {}),
    },
)

# 为 SQLite 连接启用 WAL 模式 + 忙等待超时，避免并发写入时 database is locked
if "sqlite" in settings.workflow_db_url:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

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
        # 创建历史运行记录归档表（如果尚未存在）
        try:
            from .models import RunHistoryArchive
            await conn.run_sync(
                lambda sync_conn: RunHistoryArchive.__table__.create(sync_conn, checkfirst=True)
            )
        except Exception:
            pass

        # 为已有数据库添加新列（避免旧表缺失字段报错）
        for col_sql in [
            "ALTER TABLE workflows ADD COLUMN is_published BOOLEAN DEFAULT 0 NOT NULL",
            "ALTER TABLE workflow_custom_node_schemas ADD COLUMN subcategory VARCHAR(50) DEFAULT '' NOT NULL",
            "ALTER TABLE workflow_model_configs ADD COLUMN subcategory VARCHAR(50) DEFAULT '' NOT NULL",
        ]:
            try:
                await conn.run_sync(
                    lambda sync_conn, sql=col_sql: sync_conn.exec_driver_sql(sql)
                )
            except Exception:
                pass  # 列已存在则忽略
