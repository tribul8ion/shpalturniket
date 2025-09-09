"""
API для управления мероприятиями
"""

from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select

from ..core.db import get_session
from ..models.event import (
    EventCategory,
    EventDevice,
    EventCategoryCreate,
    EventCategoryUpdate,
    EventDeviceUpdate,
    EventCategoryWithDevices
)
from ..models.log import DeviceStatusLog
from ..core.db import get_session

router = APIRouter()

@router.get("/categories", response_model=List[EventCategoryWithDevices], summary="Получить все категории мероприятий")
async def get_event_categories(session: Session = Depends(get_session)):
    """Получить все категории мероприятий с устройствами"""
    try:
        # Получаем все категории
        categories = session.exec(select(EventCategory)).all()
        
        result = []
        for category in categories:
            # Получаем устройства для категории
            devices = session.exec(
                select(EventDevice).where(EventDevice.event_category_id == category.id)
            ).all()
            
            enabled_count = sum(1 for device in devices if device.is_enabled)
            
            category_with_devices = EventCategoryWithDevices(
                **category.dict(),
                devices=devices,
                enabled_devices_count=enabled_count,
                total_devices_count=len(devices)
            )
            result.append(category_with_devices)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения категорий: {e}")


@router.get("/history", summary="История статусов устройств (последние N)")
async def get_status_history(limit: int = 200, session: Session = Depends(get_session)):
    try:
        # SQLite не поддерживает легко ORDER BY + LIMIT с SQLModel без сырых выражений,
        # но sqlmodel/select поддерживает order_by
        logs = session.exec(
            select(DeviceStatusLog).order_by(DeviceStatusLog.created_at.desc()).limit(limit)
        ).all()
        # Преобразуем в простой список словарей
        return [
            {
                "id": log.id,
                "device_id": log.device_id,
                "ip": log.ip,
                "status": log.status,
                "response_ms": log.response_ms,
                "category": log.category,
                "timestamp": log.created_at.isoformat(),
            }
            for log in logs
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения истории: {e}")


@router.get("/stats/summary", summary="Сводная статистика по истории")
async def get_stats_summary(hours: int = 24, session: Session = Depends(get_session)):
    try:
        from datetime import datetime, timedelta
        since = datetime.utcnow() - timedelta(hours=hours)
        logs = session.exec(
            select(DeviceStatusLog).where(DeviceStatusLog.created_at >= since)
        ).all()
        total_checks = len(logs)
        online = sum(1 for l in logs if l.status == "online")
        offline = sum(1 for l in logs if l.status == "offline")
        availability = round((online / total_checks * 100) if total_checks else 0, 1)
        # Группировка по устройствам (последний статус)
        last_by_device = {}
        for l in logs:
            if l.device_id not in last_by_device or last_by_device[l.device_id].created_at < l.created_at:
                last_by_device[l.device_id] = l
        current_online = sum(1 for l in last_by_device.values() if l.status == "online")
        current_offline = sum(1 for l in last_by_device.values() if l.status == "offline")
        return {
            "window_hours": hours,
            "total_checks": total_checks,
            "online_checks": online,
            "offline_checks": offline,
            "availability_percentage": availability,
            "current_online": current_online,
            "current_offline": current_offline,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка вычисления статистики: {e}")

@router.post("/categories", response_model=EventCategory, summary="Создать категорию мероприятия")
async def create_event_category(
    category_data: EventCategoryCreate,
    session: Session = Depends(get_session)
):
    """Создать новую категорию мероприятия"""
    try:
        # Проверяем, что категория с таким именем не существует
        existing = session.exec(
            select(EventCategory).where(EventCategory.name == category_data.name)
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="Категория с таким именем уже существует")
        
        category = EventCategory(**category_data.dict())
        session.add(category)
        session.commit()
        session.refresh(category)
        
        return category
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания категории: {e}")

@router.put("/categories/{category_id}", response_model=EventCategory, summary="Обновить категорию мероприятия")
async def update_event_category(
    category_id: int,
    category_data: EventCategoryUpdate,
    session: Session = Depends(get_session)
):
    """Обновить категорию мероприятия"""
    try:
        category = session.get(EventCategory, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Категория не найдена")
        
        # Обновляем только переданные поля
        update_data = category_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(category, field, value)
        
        session.add(category)
        session.commit()
        session.refresh(category)
        
        return category
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обновления категории: {e}")

@router.delete("/categories/{category_id}", summary="Удалить категорию мероприятия")
async def delete_event_category(
    category_id: int,
    session: Session = Depends(get_session)
):
    """Удалить категорию мероприятия"""
    try:
        category = session.get(EventCategory, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Категория не найдена")
        
        # Удаляем связанные устройства
        devices = session.exec(
            select(EventDevice).where(EventDevice.event_category_id == category_id)
        ).all()
        
        for device in devices:
            session.delete(device)
        
        session.delete(category)
        session.commit()
        
        return {"message": "Категория удалена успешно"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка удаления категории: {e}")

@router.get("/categories/{category_id}/devices", response_model=List[EventDevice], summary="Получить устройства категории")
async def get_category_devices(
    category_id: int,
    session: Session = Depends(get_session)
):
    """Получить устройства категории мероприятия"""
    try:
        category = session.get(EventCategory, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Категория не найдена")
        
        devices = session.exec(
            select(EventDevice).where(EventDevice.event_category_id == category_id)
        ).all()
        
        return devices
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения устройств: {e}")

@router.post("/categories/{category_id}/devices", summary="Добавить устройства в категорию")
async def add_devices_to_category(
    category_id: int,
    device_updates: List[EventDeviceUpdate],
    session: Session = Depends(get_session)
):
    """Добавить/обновить устройства в категории мероприятия"""
    try:
        category = session.get(EventCategory, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Категория не найдена")
        
        # Удаляем существующие устройства категории
        existing_devices = session.exec(
            select(EventDevice).where(EventDevice.event_category_id == category_id)
        ).all()
        
        for device in existing_devices:
            session.delete(device)
        
        # Добавляем новые устройства
        for device_update in device_updates:
            event_device = EventDevice(
                event_category_id=category_id,
                device_id=device_update.device_id,
                is_enabled=device_update.is_enabled
            )
            session.add(event_device)
        
        session.commit()
        
        return {"message": f"Добавлено {len(device_updates)} устройств в категорию"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка добавления устройств: {e}")

@router.get("/devices/available", summary="Получить доступные устройства")
async def get_available_devices():
    """Получить список всех доступных устройств из конфигурации"""
    try:
        import json
        from pathlib import Path
        
        # Читаем IP_list.json из каталога backend
        BASE_DIR = Path(__file__).parent.parent.parent
        ip_list_path = BASE_DIR / "IP_list.json"
        
        if not ip_list_path.exists():
            return {"devices": []}
        
        with open(ip_list_path, 'r', encoding='utf-8') as f:
            ip_data = json.load(f)
        
        devices = []
        for device_id, device_info in ip_data.items():
            if len(device_info) >= 3:
                ip, description, enabled = device_info[0], device_info[1], bool(int(device_info[2]))
                devices.append({
                    "device_id": device_id,
                    "ip": ip,
                    "description": description,
                    "enabled": enabled
                })
        
        return {"devices": devices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения устройств: {e}")
