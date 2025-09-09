"""
Сервис для работы с категориями мероприятий
Управление группировкой устройств для различных событий
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from sqlmodel import Session, select

from ..core.db import get_session
from ..models.event import EventCategory, EventDevice, EventCategoryWithDevices
from ..services.monitoring import monitoring_service
from ..utils.events_bus import event_manager

logger = logging.getLogger(__name__)


class EventCategoryService:
    """Сервис для управления категориями мероприятий"""
    
    def __init__(self):
        self.active_categories: Dict[int, Dict[str, Any]] = {}
        self.category_monitors: Dict[int, List[str]] = {}  # category_id -> [device_ids]
    
    def _load_available_devices(self) -> List[Dict[str, Any]]:
        """Загрузить доступные устройства из конфигурации"""
        try:
            BASE_DIR = Path(__file__).parent.parent.parent.parent
            ip_list_path = BASE_DIR / "IP_list.json"
            
            if not ip_list_path.exists():
                return []
            
            with open(ip_list_path, 'r', encoding='utf-8') as f:
                ip_data = json.load(f)
            
            devices = []
            for device_id, device_info in ip_data.items():
                if isinstance(device_info, list) and len(device_info) >= 2:
                    ip = device_info[0]
                    description = device_info[1]
                    enabled = True
                    if len(device_info) >= 3:
                        try:
                            enabled = bool(int(device_info[2]))
                        except (ValueError, IndexError):
                            enabled = True
                    
                    devices.append({
                        "device_id": device_id,
                        "ip": ip,
                        "description": description,
                        "enabled": enabled
                    })
            
            return devices
            
        except Exception as e:
            logger.error(f"Ошибка загрузки доступных устройств: {e}")
            return []
    
    async def get_categories_with_devices(self, session: Session) -> List[EventCategoryWithDevices]:
        """Получить все категории с устройствами"""
        try:
            categories = session.exec(select(EventCategory)).all()
            
            result = []
            for category in categories:
                # Получаем устройства для категории
                devices = session.exec(
                    select(EventDevice).where(EventDevice.event_category_id == category.id)
                ).all()
                
                enabled_count = sum(1 for device in devices if device.is_enabled)
                
                category_with_devices = EventCategoryWithDevices(
                    id=category.id,
                    name=category.name,
                    description=category.description,
                    is_active=category.is_active,
                    created_at=category.created_at,
                    updated_at=category.updated_at,
                    devices=list(devices),
                    enabled_devices_count=enabled_count,
                    total_devices_count=len(devices)
                )
                result.append(category_with_devices)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка получения категорий: {e}")
            return []
    
    async def create_category(self, session: Session, name: str, description: str = None) -> EventCategory:
        """Создать новую категорию мероприятия"""
        try:
            # Проверяем уникальность имени
            existing = session.exec(
                select(EventCategory).where(EventCategory.name == name)
            ).first()
            
            if existing:
                raise ValueError(f"Категория с именем '{name}' уже существует")
            
            category = EventCategory(
                name=name,
                description=description or f"Категория мероприятия: {name}",
                is_active=True
            )
            
            session.add(category)
            session.commit()
            session.refresh(category)
            
            # Отправляем событие
            await event_manager.publish({
                "type": "category_created",
                "data": {
                    "category_id": category.id,
                    "name": category.name,
                    "description": category.description,
                    "timestamp": datetime.utcnow().isoformat()
                }
            })
            
            logger.info(f"Создана категория мероприятия: {name} (ID: {category.id})")
            return category
            
        except Exception as e:
            logger.error(f"Ошибка создания категории: {e}")
            raise
    
    async def update_category(self, session: Session, category_id: int, 
                            name: str = None, description: str = None, 
                            is_active: bool = None) -> EventCategory:
        """Обновить категорию мероприятия"""
        try:
            category = session.get(EventCategory, category_id)
            if not category:
                raise ValueError(f"Категория с ID {category_id} не найдена")
            
            # Обновляем поля
            if name is not None:
                # Проверяем уникальность нового имени
                existing = session.exec(
                    select(EventCategory).where(
                        EventCategory.name == name,
                        EventCategory.id != category_id
                    )
                ).first()
                
                if existing:
                    raise ValueError(f"Категория с именем '{name}' уже существует")
                
                category.name = name
            
            if description is not None:
                category.description = description
            
            if is_active is not None:
                old_active = category.is_active
                category.is_active = is_active
                
                # Если категория деактивирована, останавливаем мониторинг
                if old_active and not is_active:
                    await self.stop_category_monitoring(category_id)
                # Если активирована, запускаем мониторинг
                elif not old_active and is_active:
                    await self.start_category_monitoring(session, category_id)
            
            category.updated_at = datetime.utcnow()
            
            session.add(category)
            session.commit()
            session.refresh(category)
            
            # Отправляем событие
            await event_manager.publish({
                "type": "category_updated",
                "data": {
                    "category_id": category.id,
                    "name": category.name,
                    "description": category.description,
                    "is_active": category.is_active,
                    "timestamp": datetime.utcnow().isoformat()
                }
            })
            
            logger.info(f"Обновлена категория мероприятия: {category.name} (ID: {category.id})")
            return category
            
        except Exception as e:
            logger.error(f"Ошибка обновления категории: {e}")
            raise
    
    async def delete_category(self, session: Session, category_id: int) -> bool:
        """Удалить категорию мероприятия"""
        try:
            category = session.get(EventCategory, category_id)
            if not category:
                raise ValueError(f"Категория с ID {category_id} не найдена")
            
            # Останавливаем мониторинг категории
            await self.stop_category_monitoring(category_id)
            
            # Удаляем связанные устройства
            devices = session.exec(
                select(EventDevice).where(EventDevice.event_category_id == category_id)
            ).all()
            
            for device in devices:
                session.delete(device)
            
            # Удаляем категорию
            category_name = category.name
            session.delete(category)
            session.commit()
            
            # Отправляем событие
            await event_manager.publish({
                "type": "category_deleted",
                "data": {
                    "category_id": category_id,
                    "name": category_name,
                    "devices_count": len(devices),
                    "timestamp": datetime.utcnow().isoformat()
                }
            })
            
            logger.info(f"Удалена категория мероприятия: {category_name} (ID: {category_id})")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка удаления категории: {e}")
            raise
    
    async def update_category_devices(self, session: Session, category_id: int, 
                                    device_updates: List[Dict[str, Any]]) -> int:
        """Обновить устройства в категории"""
        try:
            category = session.get(EventCategory, category_id)
            if not category:
                raise ValueError(f"Категория с ID {category_id} не найдена")
            
            # Удаляем существующие устройства
            existing_devices = session.exec(
                select(EventDevice).where(EventDevice.event_category_id == category_id)
            ).all()
            
            for device in existing_devices:
                session.delete(device)
            
            # Добавляем новые устройства
            added_count = 0
            for device_update in device_updates:
                event_device = EventDevice(
                    event_category_id=category_id,
                    device_id=device_update["device_id"],
                    is_enabled=device_update.get("is_enabled", True)
                )
                session.add(event_device)
                added_count += 1
            
            session.commit()
            
            # Перезапускаем мониторинг категории если она активна
            if category.is_active:
                await self.restart_category_monitoring(session, category_id)
            
            # Отправляем событие
            await event_manager.publish({
                "type": "category_devices_updated",
                "data": {
                    "category_id": category_id,
                    "category_name": category.name,
                    "devices_count": added_count,
                    "timestamp": datetime.utcnow().isoformat()
                }
            })
            
            logger.info(f"Обновлены устройства категории {category.name}: {added_count} устройств")
            return added_count
            
        except Exception as e:
            logger.error(f"Ошибка обновления устройств категории: {e}")
            raise
    
    async def start_category_monitoring(self, session: Session, category_id: int) -> bool:
        """Запустить мониторинг категории"""
        try:
            category = session.get(EventCategory, category_id)
            if not category or not category.is_active:
                return False
            
            # Получаем устройства категории
            devices = session.exec(
                select(EventDevice).where(
                    EventDevice.event_category_id == category_id,
                    EventDevice.is_enabled == True
                )
            ).all()
            
            if not devices:
                logger.warning(f"В категории {category.name} нет активных устройств для мониторинга")
                return False
            
            device_ids = [device.device_id for device in devices]
            self.category_monitors[category_id] = device_ids
            
            # Добавляем в активные категории
            self.active_categories[category_id] = {
                "name": category.name,
                "description": category.description,
                "device_count": len(device_ids),
                "started_at": datetime.utcnow().isoformat()
            }
            
            # Отправляем событие
            await event_manager.publish({
                "type": "category_monitoring_started",
                "data": {
                    "category_id": category_id,
                    "category_name": category.name,
                    "devices_count": len(device_ids),
                    "device_ids": device_ids,
                    "timestamp": datetime.utcnow().isoformat()
                }
            })
            
            logger.info(f"Запущен мониторинг категории {category.name}: {len(device_ids)} устройств")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запуска мониторинга категории: {e}")
            return False
    
    async def stop_category_monitoring(self, category_id: int) -> bool:
        """Остановить мониторинг категории"""
        try:
            if category_id not in self.active_categories:
                return False
            
            category_info = self.active_categories.pop(category_id)
            device_ids = self.category_monitors.pop(category_id, [])
            
            # Отправляем событие
            await event_manager.publish({
                "type": "category_monitoring_stopped",
                "data": {
                    "category_id": category_id,
                    "category_name": category_info.get("name", "Unknown"),
                    "devices_count": len(device_ids),
                    "timestamp": datetime.utcnow().isoformat()
                }
            })
            
            logger.info(f"Остановлен мониторинг категории {category_info.get('name', 'Unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка остановки мониторинга категории: {e}")
            return False
    
    async def restart_category_monitoring(self, session: Session, category_id: int) -> bool:
        """Перезапустить мониторинг категории"""
        await self.stop_category_monitoring(category_id)
        return await self.start_category_monitoring(session, category_id)
    
    async def get_category_statistics(self, session: Session, category_id: int) -> Dict[str, Any]:
        """Получить статистику по категории"""
        try:
            category = session.get(EventCategory, category_id)
            if not category:
                raise ValueError(f"Категория с ID {category_id} не найдена")
            
            # Получаем устройства категории
            devices = session.exec(
                select(EventDevice).where(EventDevice.event_category_id == category_id)
            ).all()
            
            # Получаем статусы устройств из мониторинга
            monitoring_status = monitoring_service.get_status()
            monitors = monitoring_status.get("monitors", {})
            
            device_stats = []
            online_count = 0
            offline_count = 0
            enabled_count = 0
            
            for device in devices:
                if device.is_enabled:
                    enabled_count += 1
                
                monitor = monitors.get(device.device_id)
                if monitor:
                    status = monitor["current_status"]
                    if status == "online":
                        online_count += 1
                    elif status == "offline":
                        offline_count += 1
                    
                    device_stats.append({
                        "device_id": device.device_id,
                        "is_enabled": device.is_enabled,
                        "status": status,
                        "ip": monitor["ip"],
                        "response_time": monitor["response_time"],
                        "last_check": monitor["last_check"]
                    })
                else:
                    device_stats.append({
                        "device_id": device.device_id,
                        "is_enabled": device.is_enabled,
                        "status": "unknown",
                        "ip": None,
                        "response_time": None,
                        "last_check": None
                    })
            
            total_devices = len(devices)
            availability_percentage = (online_count / enabled_count * 100) if enabled_count > 0 else 0
            
            return {
                "category_id": category_id,
                "name": category.name,
                "description": category.description,
                "is_active": category.is_active,
                "total_devices": total_devices,
                "enabled_devices": enabled_count,
                "disabled_devices": total_devices - enabled_count,
                "online_devices": online_count,
                "offline_devices": offline_count,
                "availability_percentage": round(availability_percentage, 1),
                "is_monitoring": category_id in self.active_categories,
                "devices": device_stats,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики категории: {e}")
            raise
    
    async def initialize_active_categories(self):
        """Инициализировать активные категории при запуске"""
        try:
            with next(get_session()) as session:
                # Получаем все активные категории
                active_categories = session.exec(
                    select(EventCategory).where(EventCategory.is_active == True)
                ).all()
                
                for category in active_categories:
                    await self.start_category_monitoring(session, category.id)
                
                logger.info(f"Инициализировано {len(active_categories)} активных категорий мониторинга")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации активных категорий: {e}")
    
    def get_active_categories_status(self) -> Dict[str, Any]:
        """Получить статус активных категорий"""
        return {
            "active_categories_count": len(self.active_categories),
            "active_categories": self.active_categories,
            "total_monitored_devices": sum(len(devices) for devices in self.category_monitors.values()),
            "category_monitors": self.category_monitors
        }


# Глобальный экземпляр сервиса
event_category_service = EventCategoryService()