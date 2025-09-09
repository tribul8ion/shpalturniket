"""
База данных
"""

from sqlmodel import SQLModel, create_engine, Session
from .config import settings

# Создаем движок базы данных
engine = create_engine(
    f"sqlite:///{settings['DB_PATH']}",
    echo=settings.get('DB_ECHO', False)
)

def create_db_and_tables():
    """Создать базу данных и таблицы"""
    # Импортируем все модели
    from ..models.device import Device
    from ..models.theme import ThemePreset
    from ..models.scenario import Scenario
    from ..models.event import EventCategory, EventDevice
    from ..models.log import DeviceStatusLog
    
    # Создаем все таблицы
    SQLModel.metadata.create_all(engine)

def get_session():
    """Получить сессию базы данных"""
    with Session(engine) as session:
        yield session