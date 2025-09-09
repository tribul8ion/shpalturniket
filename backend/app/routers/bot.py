"""
Router для управления Telegram ботом
Интеграция с новым сервисом бота
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from ..services.telegram_bot import telegram_bot_service

router = APIRouter()

class BotStatus(BaseModel):
    """Статус бота"""
    is_running: bool
    uptime: Optional[str] = None
    messages_sent: int = 0
    commands_processed: int = 0
    authorized_users: int = 0
    notification_subscribers: int = 0
    last_start: Optional[str] = None
    error: Optional[str] = None

class BotConfig(BaseModel):
    """Конфигурация бота"""
    token: str
    time_connect: int
    chat_ids: List[int]

# Состояние задач бота
bot_task: Optional[asyncio.Task] = None
bot_start_time: Optional[datetime] = None

def _read_bot_config() -> Dict[str, Any]:
    """Читает конфигурацию бота из config.json"""
    BASE_DIR = Path(__file__).parent.parent.parent.parent
    config_path = BASE_DIR / "config.json"
    if not config_path.exists():
        return {}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _write_bot_config(config_data: Dict[str, Any]):
    """Записывает конфигурацию бота в config.json"""
    BASE_DIR = Path(__file__).parent.parent.parent.parent
    config_path = BASE_DIR / "config.json"
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)

@router.get("/status", response_model=BotStatus, summary="Получить статус Telegram бота")
async def get_bot_status():
    """Получить текущий статус бота"""
    status = telegram_bot_service.get_status()
    
    return BotStatus(
        is_running=status["is_running"],
        uptime=status["uptime"],
        messages_sent=status["messages_sent"],
        commands_processed=status["commands_processed"],
        authorized_users=status["authorized_users"],
        notification_subscribers=status["notification_subscribers"],
        last_start=status["start_time"]
    )

@router.post("/start", summary="Запустить Telegram бота")
async def start_bot(background_tasks: BackgroundTasks):
    """Запустить Telegram бота"""
    global bot_task, bot_start_time
    
    if telegram_bot_service.is_running:
        return {"success": False, "message": "Бот уже запущен"}
    
    try:
        # Запускаем бота в фоновой задаче
        bot_task = asyncio.create_task(telegram_bot_service.start())
        bot_start_time = datetime.now()
        
        # Ждем немного, чтобы убедиться что бот запустился
        await asyncio.sleep(1)
        
        if telegram_bot_service.is_running:
            return {"success": True, "message": "Telegram бот запущен успешно"}
        else:
            return {"success": False, "message": "Не удалось запустить бота"}
        
    except Exception as e:
        return {"success": False, "message": f"Ошибка запуска бота: {e}"}

@router.post("/stop", summary="Остановить Telegram бота")
async def stop_bot():
    """Остановить Telegram бота"""
    global bot_task
    
    if not telegram_bot_service.is_running:
        return {"success": False, "message": "Бот не запущен"}
    
    try:
        await telegram_bot_service.stop()
        
        if bot_task:
            bot_task.cancel()
            try:
                await bot_task
            except asyncio.CancelledError:
                pass
            bot_task = None
        
        return {"success": True, "message": "Telegram бот остановлен успешно"}
        
    except Exception as e:
        return {"success": False, "message": f"Ошибка остановки бота: {e}"}

@router.get("/config", summary="Получить конфигурацию бота")
async def get_bot_config():
    """Получить конфигурацию бота"""
    config_data = _read_bot_config()
    
    chat_ids = config_data.get("chat_id", [])
    if isinstance(chat_ids, (str, int)):
        chat_ids = [int(chat_ids)]
    elif isinstance(chat_ids, list):
        chat_ids = [int(x) for x in chat_ids if str(x).isdigit()]
    
    return {
        "exists": bool(config_data),
        "token": config_data.get("TOKEN", ""),
        "time_connect": int(config_data.get("time_connect", 50)),
        "chat_ids": chat_ids
    }

@router.put("/config", summary="Обновить конфигурацию бота")
async def update_bot_config(config: BotConfig):
    """Обновить конфигурацию бота"""
    try:
        config_data = _read_bot_config()
        config_data["TOKEN"] = config.token
        config_data["time_connect"] = str(config.time_connect)
        config_data["chat_id"] = config.chat_ids
        
        _write_bot_config(config_data)
        
        # Перезагружаем конфигурацию в сервисе
        telegram_bot_service.config = telegram_bot_service._load_config()
        
        return {"success": True, "message": "Конфигурация бота обновлена успешно"}
        
    except Exception as e:
        return {"success": False, "message": f"Ошибка обновления конфигурации: {e}"}

@router.get("/logs", summary="Получить логи бота")
async def get_bot_logs():
    """Получить логи бота"""
    try:
        logs = []
        
        # Читаем логи из файла, если он существует
        BASE_DIR = Path(__file__).parent.parent.parent.parent
        log_file_path = BASE_DIR / "bot.log"
        
        if log_file_path.exists():
            with open(log_file_path, 'r', encoding='utf-8') as f:
                # Читаем последние 100 строк
                all_lines = f.readlines()
                logs = [line.strip() for line in all_lines[-100:] if line.strip()]
        
        return {"logs": logs, "message": "Логи получены", "success": True}
        
    except Exception as e:
        return {"logs": [], "error": str(e), "success": False}

@router.delete("/logs", summary="Очистить логи бота")
async def clear_bot_logs():
    """Очистить файл логов бота"""
    try:
        BASE_DIR = Path(__file__).parent.parent.parent.parent
        log_file_path = BASE_DIR / "bot.log"
        
        if log_file_path.exists():
            # Обрезаем файл до нуля
            with open(log_file_path, 'w', encoding='utf-8') as f:
                f.truncate(0)
        
        return {"success": True, "message": "Логи очищены"}
    except Exception as e:
        return {"success": False, "message": f"Ошибка очистки логов: {e}"}

@router.post("/restart", summary="Перезапустить Telegram бота")
async def restart_bot(background_tasks: BackgroundTasks):
    """Перезапустить Telegram бота"""
    # Сначала останавливаем
    if telegram_bot_service.is_running:
        stop_result = await stop_bot()
        if not stop_result.get("success"):
            return stop_result
    
    # Ждем немного
    await asyncio.sleep(1)
    
    # Затем запускаем
    start_result = await start_bot(background_tasks)
    
    if start_result.get("success"):
        return {"success": True, "message": "Telegram бот перезапущен успешно"}
    else:
        return {"success": False, "message": f"Ошибка перезапуска: {start_result.get('message')}"}
