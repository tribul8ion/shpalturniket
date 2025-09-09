"""
Система событий для real-time уведомлений
Server-Sent Events для передачи данных на фронтенд
"""

import asyncio
import json
from typing import Dict, Any, List, Callable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class EventManager:
    """Менеджер событий для Server-Sent Events"""
    
    def __init__(self):
        self._subscribers: List[Callable] = []
        self._event_history: List[Dict[str, Any]] = []
        self._max_history = 100
        
    async def subscribe(self, callback: Callable):
        """Подписаться на события"""
        self._subscribers.append(callback)
        logger.info(f"Новый подписчик добавлен. Всего подписчиков: {len(self._subscribers)}")
        
    async def unsubscribe(self, callback: Callable):
        """Отписаться от событий"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            logger.info(f"Подписчик удален. Осталось подписчиков: {len(self._subscribers)}")
            
    async def publish(self, event: Dict[str, Any]):
        """Опубликовать событие всем подписчикам"""
        try:
            # Добавляем timestamp если его нет
            if 'timestamp' not in event:
                event['timestamp'] = datetime.utcnow().isoformat()
            
            # Сохраняем в историю
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]
            
            # Отправляем всем подписчикам
            if self._subscribers:
                logger.debug(f"Отправка события {event.get('type', 'unknown')} для {len(self._subscribers)} подписчиков")
                
                # Создаем копии для каждого подписчика
                failed_subscribers = []
                for subscriber in self._subscribers[:]:  # Создаем копию списка
                    try:
                        await subscriber(event)
                    except Exception as e:
                        logger.error(f"Ошибка отправки события подписчику: {e}")
                        failed_subscribers.append(subscriber)
                
                # Удаляем неработающих подписчиков
                for failed in failed_subscribers:
                    await self.unsubscribe(failed)
                    
        except Exception as e:
            logger.error(f"Ошибка публикации события: {e}")
    
    def get_recent_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить последние события"""
        return self._event_history[-limit:] if self._event_history else []
    
    def get_subscriber_count(self) -> int:
        """Получить количество активных подписчиков"""
        return len(self._subscribers)


class DeviceEventManager:
    """Специализированный менеджер для событий устройств"""
    
    def __init__(self, event_manager: EventManager):
        self.event_manager = event_manager
        self._device_states: Dict[str, Dict[str, Any]] = {}
        
    async def device_status_changed(self, device_id: str, old_status: str, new_status: str, 
                                  ip: str, response_time: float = None):
        """Уведомить об изменении статуса устройства"""
        
        # Сохраняем состояние
        self._device_states[device_id] = {
            'status': new_status,
            'ip': ip,
            'response_time': response_time,
            'last_update': datetime.utcnow().isoformat()
        }
        
        # Определяем тип события
        event_type = 'device_status'
        if old_status != new_status:
            if new_status == 'online' and old_status == 'offline':
                event_type = 'device_recovery'
            elif new_status == 'offline' and old_status == 'online':
                event_type = 'device_failure'
        
        # Публикуем событие
        await self.event_manager.publish({
            'type': event_type,
            'data': {
                'device_id': device_id,
                'ip': ip,
                'old_status': old_status,
                'new_status': new_status,
                'status': new_status,
                'response_time': response_time,
                'timestamp': datetime.utcnow().isoformat()
            }
        })
        
    async def ping_completed(self, results: List[Dict[str, Any]]):
        """Уведомить о завершении массового пинга"""
        online_count = sum(1 for r in results if r.get('status') == 'online')
        offline_count = len(results) - online_count
        
        await self.event_manager.publish({
            'type': 'ping_completed',
            'data': {
                'total_devices': len(results),
                'online_count': online_count,
                'offline_count': offline_count,
                'results': results,
                'timestamp': datetime.utcnow().isoformat()
            }
        })
    
    def get_device_states(self) -> Dict[str, Dict[str, Any]]:
        """Получить текущие состояния всех устройств"""
        return self._device_states.copy()


# Глобальные экземпляры
event_manager = EventManager()
device_event_manager = DeviceEventManager(event_manager)


class SSEResponse:
    """Класс для Server-Sent Events ответов"""
    
    def __init__(self):
        self.queue = asyncio.Queue()
        self.connected = True
        
    async def send_event(self, event: Dict[str, Any]):
        """Отправить событие клиенту"""
        if not self.connected:
            return
            
        try:
            # Форматируем событие для SSE
            event_data = json.dumps(event, ensure_ascii=False)
            sse_data = f"data: {event_data}\n\n"
            await self.queue.put(sse_data)
        except Exception as e:
            logger.error(f"Ошибка отправки SSE события: {e}")
            self.connected = False
    
    async def close(self):
        """Закрыть соединение"""
        self.connected = False
        await self.queue.put(None)  # Сигнал завершения
    
    def __aiter__(self):
        return self
        
    async def __anext__(self):
        if not self.connected:
            raise StopAsyncIteration
            
        try:
            data = await asyncio.wait_for(self.queue.get(), timeout=30.0)
            if data is None:  # Сигнал завершения
                raise StopAsyncIteration
            return data
        except asyncio.TimeoutError:
            # Отправляем keep-alive каждые 30 секунд
            return ": keep-alive\n\n"
        except Exception as e:
            logger.error(f"Ошибка в SSE итераторе: {e}")
            raise StopAsyncIteration