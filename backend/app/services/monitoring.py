"""
Сервис автоматического мониторинга турникетов
Фоновые задачи для непрерывного пинга устройств
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from icmplib import ping as icmp_ping

from ..utils.events_bus import event_manager, device_event_manager
from ..core.db import get_session
from ..models.device import Device
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


class DeviceMonitor:
    """Монитор отдельного устройства"""
    
    def __init__(self, device_id: str, ip: str, description: str = ""):
        self.device_id = device_id
        self.ip = ip
        self.description = description
        self.current_status = "unknown"
        self.last_check = None
        self.response_time = None
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        
    async def ping(self) -> Dict[str, any]:
        """Выполнить пинг устройства"""
        try:
            # Выполняем пинг в отдельном потоке
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: icmp_ping(self.ip, count=1, timeout=3)
            )
            
            is_alive = getattr(result, 'is_alive', False)
            avg_rtt = getattr(result, 'avg_rtt', None)
            
            old_status = self.current_status
            new_status = "online" if is_alive else "offline"
            
            # Обновляем состояние
            self.last_check = datetime.utcnow()
            self.response_time = int(avg_rtt * 1000) if avg_rtt else None
            
            # Подсчитываем последовательные сбои/успехи
            if new_status == "online":
                self.consecutive_failures = 0
                self.consecutive_successes += 1
            else:
                self.consecutive_successes = 0
                self.consecutive_failures += 1
            
            # Уведомляем об изменении статуса только если статус действительно изменился
            if old_status != new_status and old_status != "unknown":
                await device_event_manager.device_status_changed(
                    self.device_id, old_status, new_status, 
                    self.ip, self.response_time
                )
                logger.info(f"Устройство {self.device_id} ({self.ip}): {old_status} -> {new_status}")
            
            self.current_status = new_status
            
            return {
                "device_id": self.device_id,
                "ip": self.ip,
                "status": new_status,
                "response_time": self.response_time,
                "timestamp": self.last_check.isoformat(),
                "consecutive_failures": self.consecutive_failures,
                "consecutive_successes": self.consecutive_successes
            }
            
        except Exception as e:
            logger.error(f"Ошибка пинга устройства {self.device_id} ({self.ip}): {e}")
            
            old_status = self.current_status
            self.current_status = "error"
            self.last_check = datetime.utcnow()
            self.response_time = None
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            
            if old_status != "error" and old_status != "unknown":
                await device_event_manager.device_status_changed(
                    self.device_id, old_status, "error", self.ip, None
                )
            
            return {
                "device_id": self.device_id,
                "ip": self.ip,
                "status": "error",
                "response_time": None,
                "timestamp": self.last_check.isoformat(),
                "error": str(e),
                "consecutive_failures": self.consecutive_failures,
                "consecutive_successes": self.consecutive_successes
            }


class MonitoringService:
    """Сервис мониторинга всех устройств"""
    
    def __init__(self):
        self.monitors: Dict[str, DeviceMonitor] = {}
        self.is_running = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.ping_interval = 30  # секунд
        self.config_check_interval = 300  # 5 минут
        self.last_config_check = None
        
    def _load_devices_from_config(self) -> List[Tuple[str, str, str]]:
        """Загрузить устройства из IP_list.json"""
        try:
            BASE_DIR = Path(__file__).parent.parent.parent.parent
            ip_list_path = BASE_DIR / "IP_list.json"
            
            if not ip_list_path.exists():
                logger.warning("IP_list.json не найден")
                return []
            
            with open(ip_list_path, 'r', encoding='utf-8') as f:
                ip_data = json.load(f)
            
            devices = []
            for device_id, device_info in ip_data.items():
                if isinstance(device_info, list) and len(device_info) >= 2:
                    ip = device_info[0]
                    description = device_info[1]
                    # Проверяем, что устройство включено (если есть 3-й параметр)
                    enabled = True
                    if len(device_info) >= 3:
                        try:
                            enabled = bool(int(device_info[2]))
                        except (ValueError, IndexError):
                            enabled = True
                    
                    if enabled:
                        devices.append((device_id, ip, description))
            
            logger.info(f"Загружено {len(devices)} устройств из конфигурации")
            return devices
            
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации устройств: {e}")
            return []
    
    def _load_ping_interval(self) -> int:
        """Загрузить интервал пинга из config.json"""
        try:
            BASE_DIR = Path(__file__).parent.parent.parent.parent
            config_path = BASE_DIR / "config.json"
            
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                time_connect = config.get("time_connect", 30)
                if isinstance(time_connect, str):
                    time_connect = int(time_connect)
                
                return max(10, min(300, time_connect))  # От 10 секунд до 5 минут
            
        except Exception as e:
            logger.error(f"Ошибка загрузки интервала пинга: {e}")
        
        return 30  # По умолчанию 30 секунд
    
    async def _update_database_status(self, results: List[Dict[str, any]]):
        """Обновить статусы в базе данных"""
        try:
            # Используем контекстный менеджер для сессии
            with next(get_session()) as session:
                for result in results:
                    device_id = result["device_id"]
                    
                    # Ищем устройство в БД
                    device = session.exec(
                        select(Device).where(Device.device_id == device_id)
                    ).first()
                    
                    if device:
                        # Обновляем существующее устройство
                        device.status = result["status"]
                        device.response_ms = result["response_time"]
                        device.last_check = datetime.fromisoformat(result["timestamp"].replace('Z', '+00:00'))
                        device.updated_at = datetime.utcnow()
                        session.add(device)
                    else:
                        # Создаем новое устройство
                        device = Device(
                            device_id=device_id,
                            ip=result["ip"],
                            description=f"Автоматически добавлено из мониторинга",
                            category="Турникет",
                            status=result["status"],
                            response_ms=result["response_time"],
                            last_check=datetime.fromisoformat(result["timestamp"].replace('Z', '+00:00'))
                        )
                        session.add(device)
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Ошибка обновления БД: {e}")
    
    async def _monitoring_loop(self):
        """Основной цикл мониторинга"""
        logger.info("Запуск цикла мониторинга")
        
        while self.is_running:
            try:
                # Проверяем конфигурацию периодически
                now = datetime.utcnow()
                if (self.last_config_check is None or 
                    now - self.last_config_check > timedelta(seconds=self.config_check_interval)):
                    
                    await self._reload_configuration()
                    self.last_config_check = now
                
                # Выполняем пинг всех устройств
                if self.monitors:
                    logger.debug(f"Выполнение пинга {len(self.monitors)} устройств")
                    
                    # Запускаем все пинги параллельно
                    ping_tasks = [monitor.ping() for monitor in self.monitors.values()]
                    results = await asyncio.gather(*ping_tasks, return_exceptions=True)
                    
                    # Фильтруем успешные результаты
                    valid_results = []
                    for result in results:
                        if isinstance(result, dict):
                            valid_results.append(result)
                        else:
                            logger.error(f"Ошибка пинга: {result}")
                    
                    # Обновляем БД
                    if valid_results:
                        await self._update_database_status(valid_results)
                        
                        # Отправляем событие о завершении пинга
                        await device_event_manager.ping_completed(valid_results)
                    
                    # Статистика
                    online_count = sum(1 for r in valid_results if r["status"] == "online")
                    offline_count = len(valid_results) - online_count
                    
                    logger.debug(f"Пинг завершен: {online_count} онлайн, {offline_count} офлайн")
                
                # Ждем до следующего цикла
                await asyncio.sleep(self.ping_interval)
                
            except asyncio.CancelledError:
                logger.info("Цикл мониторинга отменен")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                await asyncio.sleep(5)  # Короткая пауза при ошибке
        
        logger.info("Цикл мониторинга завершен")
    
    async def _reload_configuration(self):
        """Перезагрузить конфигурацию устройств"""
        try:
            # Загружаем новый интервал пинга
            new_interval = self._load_ping_interval()
            if new_interval != self.ping_interval:
                self.ping_interval = new_interval
                logger.info(f"Интервал пинга изменен на {self.ping_interval} секунд")
            
            # Загружаем устройства
            devices = self._load_devices_from_config()
            
            # Обновляем мониторы
            new_monitors = {}
            for device_id, ip, description in devices:
                if device_id in self.monitors:
                    # Обновляем существующий монитор
                    monitor = self.monitors[device_id]
                    monitor.ip = ip
                    monitor.description = description
                    new_monitors[device_id] = monitor
                else:
                    # Создаем новый монитор
                    new_monitors[device_id] = DeviceMonitor(device_id, ip, description)
                    logger.info(f"Добавлен новый монитор для {device_id} ({ip})")
            
            # Удаляем старые мониторы
            removed = set(self.monitors.keys()) - set(new_monitors.keys())
            for device_id in removed:
                logger.info(f"Удален монитор для {device_id}")
            
            self.monitors = new_monitors
            
        except Exception as e:
            logger.error(f"Ошибка перезагрузки конфигурации: {e}")
    
    async def start(self):
        """Запустить мониторинг"""
        if self.is_running:
            logger.warning("Мониторинг уже запущен")
            return
        
        logger.info("Запуск сервиса мониторинга")
        
        # Загружаем конфигурацию
        await self._reload_configuration()
        
        # Запускаем цикл мониторинга
        self.is_running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # Отправляем событие о запуске
        await event_manager.publish({
            "type": "monitoring_started",
            "data": {
                "devices_count": len(self.monitors),
                "ping_interval": self.ping_interval,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
        
        logger.info(f"Мониторинг запущен для {len(self.monitors)} устройств")
    
    async def stop(self):
        """Остановить мониторинг"""
        if not self.is_running:
            logger.warning("Мониторинг не запущен")
            return
        
        logger.info("Остановка сервиса мониторинга")
        
        self.is_running = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Отправляем событие об остановке
        await event_manager.publish({
            "type": "monitoring_stopped",
            "data": {
                "timestamp": datetime.utcnow().isoformat()
            }
        })
        
        logger.info("Мониторинг остановлен")
    
    async def ping_all_now(self) -> List[Dict[str, any]]:
        """Выполнить немедленный пинг всех устройств"""
        if not self.monitors:
            await self._reload_configuration()
        
        if not self.monitors:
            return []
        
        logger.info(f"Выполнение немедленного пинга {len(self.monitors)} устройств")
        
        # Запускаем все пинги параллельно
        ping_tasks = [monitor.ping() for monitor in self.monitors.values()]
        results = await asyncio.gather(*ping_tasks, return_exceptions=True)
        
        # Фильтруем успешные результаты
        valid_results = []
        for result in results:
            if isinstance(result, dict):
                valid_results.append(result)
            else:
                logger.error(f"Ошибка пинга: {result}")
        
        # Обновляем БД
        if valid_results:
            await self._update_database_status(valid_results)
            await device_event_manager.ping_completed(valid_results)
        
        return valid_results
    
    def get_status(self) -> Dict[str, any]:
        """Получить статус сервиса мониторинга"""
        return {
            "is_running": self.is_running,
            "devices_count": len(self.monitors),
            "ping_interval": self.ping_interval,
            "last_config_check": self.last_config_check.isoformat() if self.last_config_check else None,
            "monitors": {
                device_id: {
                    "ip": monitor.ip,
                    "current_status": monitor.current_status,
                    "last_check": monitor.last_check.isoformat() if monitor.last_check else None,
                    "response_time": monitor.response_time,
                    "consecutive_failures": monitor.consecutive_failures,
                    "consecutive_successes": monitor.consecutive_successes
                }
                for device_id, monitor in self.monitors.items()
            }
        }


# Глобальный экземпляр сервиса мониторинга
monitoring_service = MonitoringService()