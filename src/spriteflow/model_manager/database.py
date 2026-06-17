"""模型管理模块专用数据库引擎"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from ..config import settings

DATABASE_URL = "sqlite+aiosqlite:///data/model_manager.db"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取模型管理数据库会话"""
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
    """初始化模型管理数据库 — 创建所有表并执行迁移"""
    from .models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_model_defaults()


async def _migrate_model_defaults():
    """迁移 ModelDefault 表：从单主键 category 迁移到复合主键 (category, subcategory)"""
    import sqlite3
    import os
    from urllib.parse import urlparse

    parsed = urlparse(DATABASE_URL)
    db_path = parsed.path.lstrip("/")  # SQLite 文件路径
    # 如果是 aiosqlite，路径在 hostname 或 path 中
    if not db_path or not os.path.exists(db_path):
        # 尝试从路径中提取
        db_path = "data/model_manager.db"

    # 使用同步 sqlite3 检查并迁移
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute("PRAGMA table_info(model_defaults)")
        columns = [row[1] for row in cur.fetchall()]
        if "subcategory" not in columns:
            # 旧表需要迁移
            # 1. 创建新表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS model_defaults_new (
                    category TEXT NOT NULL,
                    subcategory TEXT NOT NULL DEFAULT '',
                    model_id TEXT NOT NULL,
                    updated_at TEXT,
                    PRIMARY KEY (category, subcategory)
                )
            """)
            # 2. 复制旧数据（subcategory 默认为 ""）
            conn.execute("""
                INSERT OR IGNORE INTO model_defaults_new (category, subcategory, model_id, updated_at)
                SELECT category, '', model_id, updated_at FROM model_defaults
            """)
            # 3. 删除旧表
            conn.execute("DROP TABLE model_defaults")
            # 4. 重命名新表
            conn.execute("ALTER TABLE model_defaults_new RENAME TO model_defaults")
            conn.commit()
        conn.close()
    except Exception:
        pass  # 首次启动无旧表，正常忽略
