from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

sync_engine = create_engine(
    settings.sync_database_url,
    pool_pre_ping=True,
    future=True,
)

sync_session_factory = sessionmaker(
    sync_engine,
    expire_on_commit=False,
    class_=Session,
)


def dispose_engine() -> None:
    sync_engine.dispose()
