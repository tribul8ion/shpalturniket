"""
API для управления мероприятиями
Интеграция с сервисом категорий мероприятий
"""

from typing import List, Dict, Any
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
from ..services.event_categories import event_category_service

router = APIRouter()

@router.get("/categories", response_model=List[EventCategoryWithDevices], summary="Получить все категории мероприятий")
async def get_event_categories(session: Session = Depends(get_session)):
    """Получить все категории мероприятий с устройствами"""
    try:
        return await event_category_service.get_categories_with_devices(session)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения категорий: {e}")

@router.post("/categories", response_model=EventCategory, summary="Создать категорию мероприятия")
async def create_event_category(
    category_data: EventCategoryCreate,
    session: Session = Depends(get_session)
):
    """Создать новую категорию мероприятия"""
    try:
        return await event_category_service.create_category(
            session, category_data.name, category_data.description
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
        update_data = category_data.dict(exclude_unset=True)
        return await event_category_service.update_category(
            session, category_id, 
            name=update_data.get("name"),
            description=update_data.get("description"),
            is_active=update_data.get("is_active")
        )
    except ValueError as e:
        raise HTTPException(status_code=404 if "не найдена" in str(e) else 400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обновления категории: {e}")

@router.delete("/categories/{category_id}", summary="Удалить категорию мероприятия")
async def delete_event_category(
    category_id: int,
    session: Session = Depends(get_session)
):
    """Удалить категорию мероприятия"""
    try:
        await event_category_service.delete_category(session, category_id)
        return {"message": "Категория удалена успешно"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
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
        # Преобразуем EventDeviceUpdate в словари
        device_data = [
            {"device_id": device.device_id, "is_enabled": device.is_enabled}
            for device in device_updates
        ]
        
        count = await event_category_service.update_category_devices(
            session, category_id, device_data
        )
        return {"message": f"Добавлено {count} устройств в категорию"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка добавления устройств: {e}")

@router.get("/devices/available", summary="Получить доступные устройства")
async def get_available_devices():
    """Получить список всех доступных устройств из конфигурации"""
    try:
        devices = event_category_service._load_available_devices()
        return {"devices": devices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения устройств: {e}")

@router.get("/categories/{category_id}/statistics", summary="Получить статистику категории")
async def get_category_statistics(
    category_id: int,
    session: Session = Depends(get_session)
):
    """Получить детальную статистику по категории мероприятия"""
    try:
        return await event_category_service.get_category_statistics(session, category_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения статистики: {e}")

@router.post("/categories/{category_id}/monitoring/start", summary="Запустить мониторинг категории")
async def start_category_monitoring(
    category_id: int,
    session: Session = Depends(get_session)
):
    """Запустить мониторинг устройств категории"""
    try:
        success = await event_category_service.start_category_monitoring(session, category_id)
        if success:
            return {"message": "Мониторинг категории запущен успешно", "success": True}
        else:
            return {"message": "Не удалось запустить мониторинг категории", "success": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка запуска мониторинга: {e}")

@router.post("/categories/{category_id}/monitoring/stop", summary="Остановить мониторинг категории")
async def stop_category_monitoring(
    category_id: int
):
    """Остановить мониторинг устройств категории"""
    try:
        success = await event_category_service.stop_category_monitoring(category_id)
        if success:
            return {"message": "Мониторинг категории остановлен успешно", "success": True}
        else:
            return {"message": "Категория не была под мониторингом", "success": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка остановки мониторинга: {e}")

@router.get("/monitoring/status", summary="Получить статус мониторинга категорий")
async def get_categories_monitoring_status():
    """Получить статус мониторинга всех активных категорий"""
    try:
        return event_category_service.get_active_categories_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения статуса: {e}")
