"""
Router для событий (SSE)
"""

import asyncio
import json
import logging
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..utils.events_bus import event_manager, SSEResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/events/stream", summary="Поток событий")
async def stream_events(request: Request):
    """Поток событий в реальном времени через Server-Sent Events"""
    
    async def event_generator():
        sse_response = SSEResponse()
        
        # Подписываемся на события
        await event_manager.subscribe(sse_response.send_event)
        
        try:
            # Отправляем приветственное сообщение
            await sse_response.send_event({
                "type": "connection",
                "data": {
                    "status": "connected",
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": "Подключение к потоку событий установлено"
                }
            })
            
            # Отправляем последние события
            recent_events = event_manager.get_recent_events(5)
            for event in recent_events:
                await sse_response.send_event(event)
            
            # Основной цикл генерации событий
            async for data in sse_response:
                if await request.is_disconnected():
                    logger.info("Клиент отключился от SSE потока")
                    break
                yield data
                
        except Exception as e:
            logger.error(f"Ошибка в генераторе событий: {e}")
        finally:
            # Отписываемся от событий
            await event_manager.unsubscribe(sse_response.send_event)
            await sse_response.close()
            logger.info("SSE соединение закрыто")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control, Authorization",
            "Access-Control-Allow-Methods": "GET",
            "X-Accel-Buffering": "no",  # Nginx не буферизует SSE
        },
    )


@router.get("/events/recent", summary="Получить последние события")
async def get_recent_events(limit: int = 10):
    """Получить последние события"""
    events = event_manager.get_recent_events(limit)
    return {
        "events": events,
        "count": len(events),
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/events/stats", summary="Статистика событий")
async def get_event_stats():
    """Получить статистику системы событий"""
    return {
        "active_subscribers": event_manager.get_subscriber_count(),
        "recent_events_count": len(event_manager.get_recent_events(100)),
        "timestamp": datetime.utcnow().isoformat()
    }
