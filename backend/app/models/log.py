"""
Модели логов и истории статусов устройств
"""

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class DeviceStatusLog(SQLModel, table=True):
    """История изменений статуса устройств и результаты проверок."""

    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(index=True, max_length=50)
    ip: str = Field(max_length=45, index=True)
    status: str = Field(max_length=20, index=True)
    response_ms: Optional[int] = Field(default=None)
    event_category_id: Optional[int] = Field(default=None, index=True)
    category: Optional[str] = Field(default=None, max_length=100)
    message: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

