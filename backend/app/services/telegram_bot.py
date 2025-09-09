"""
Улучшенный Telegram бот для мониторинга турникетов
Интеграция с системой мониторинга и уведомлений
"""

import asyncio
import json
import logging
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery,
    Message
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from ..utils.events_bus import event_manager
from .monitoring import monitoring_service

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class UserStates(StatesGroup):
    """Состояния пользователя"""
    main_menu = State()
    viewing_devices = State()
    viewing_statistics = State()
    viewing_categories = State()


class TelegramBotService:
    """Сервис Telegram бота"""
    
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.is_running = False
        self.config = self._load_config()
        self.authorized_users = set()
        self.notification_subscribers = set()
        
        # Статистика бота
        self.start_time = None
        self.messages_sent = 0
        self.commands_processed = 0
        
    def _load_config(self) -> Dict[str, Any]:
        """Загрузить конфигурацию бота"""
        try:
            BASE_DIR = Path(__file__).parent.parent.parent.parent
            config_path = BASE_DIR / "config.json"
            
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            return {}
    
    def _get_authorized_chat_ids(self) -> List[int]:
        """Получить список авторизованных чатов"""
        chat_ids = self.config.get("chat_id", [])
        
        if isinstance(chat_ids, (str, int)):
            try:
                return [int(chat_ids)]
            except ValueError:
                return []
        elif isinstance(chat_ids, list):
            result = []
            for chat_id in chat_ids:
                try:
                    result.append(int(chat_id))
                except (ValueError, TypeError):
                    continue
            return result
        
        return []
    
    def _is_authorized(self, user_id: int) -> bool:
        """Проверить авторизацию пользователя"""
        authorized_ids = self._get_authorized_chat_ids()
        return user_id in authorized_ids or user_id in self.authorized_users
    
    async def _send_to_subscribers(self, message: str, parse_mode: str = "HTML"):
        """Отправить сообщение всем подписчикам"""
        if not self.bot:
            return
            
        subscribers = self.notification_subscribers.union(set(self._get_authorized_chat_ids()))
        
        for user_id in subscribers:
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=parse_mode
                )
                self.messages_sent += 1
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
    
    def _create_main_keyboard(self) -> InlineKeyboardMarkup:
        """Создать главную клавиатуру"""
        builder = InlineKeyboardBuilder()
        
        builder.row(
            InlineKeyboardButton(text="📊 Статус системы", callback_data="system_status"),
            InlineKeyboardButton(text="📈 Статистика", callback_data="statistics")
        )
        builder.row(
            InlineKeyboardButton(text="📋 Все устройства", callback_data="all_devices"),
            InlineKeyboardButton(text="🎯 Пинг сейчас", callback_data="ping_now")
        )
        builder.row(
            InlineKeyboardButton(text="🟢 Онлайн", callback_data="online_devices"),
            InlineKeyboardButton(text="🔴 Офлайн", callback_data="offline_devices")
        )
        builder.row(
            InlineKeyboardButton(text="🏗️ Категории", callback_data="categories"),
            InlineKeyboardButton(text="🔔 Уведомления", callback_data="notifications")
        )
        builder.row(
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
        )
        
        return builder.as_markup()
    
    def _format_device_list(self, devices: List[Dict[str, Any]], title: str) -> str:
        """Форматировать список устройств"""
        if not devices:
            return f"<b>{title}</b>\n\n<i>Устройства не найдены</i>"
        
        text = f"<b>{title} ({len(devices)})</b>\n\n"
        
        for device in devices[:20]:  # Ограничиваем до 20 устройств
            status_emoji = "🟢" if device["status"] == "online" else "🔴" if device["status"] == "offline" else "⚪"
            response_time = f" ({device.get('response_time', 0)}ms)" if device.get('response_time') else ""
            
            text += f"{status_emoji} <code>{device['device_id']}</code> - {device['ip']}{response_time}\n"
        
        if len(devices) > 20:
            text += f"\n<i>... и еще {len(devices) - 20} устройств</i>"
        
        return text
    
    def _format_statistics(self, status: Dict[str, Any]) -> str:
        """Форматировать статистику"""
        total = len(status.get("monitors", {}))
        online = sum(1 for m in status.get("monitors", {}).values() if m["current_status"] == "online")
        offline = total - online
        
        percentage = (online / total * 100) if total > 0 else 0
        
        # Создаем прогресс-бар
        bar_length = 10
        filled = int(percentage / 10)
        bar = "🟩" * filled + "⬜" * (bar_length - filled)
        
        uptime = "Неизвестно"
        if self.start_time:
            delta = datetime.now() - self.start_time
            hours = int(delta.total_seconds() // 3600)
            minutes = int((delta.total_seconds() % 3600) // 60)
            uptime = f"{hours}ч {minutes}м"
        
        text = f"""
<b>📊 Статистика системы мониторинга</b>

<b>🎯 Общее состояние:</b>
{bar} {percentage:.1f}%

<b>📈 Устройства:</b>
├ 📡 Всего: {total}
├ 🟢 Онлайн: {online}
├ 🔴 Офлайн: {offline}
└ ⏱️ Интервал: {status.get('ping_interval', 30)}с

<b>🤖 Бот:</b>
├ ⏰ Время работы: {uptime}
├ 📨 Отправлено сообщений: {self.messages_sent}
├ 🔧 Обработано команд: {self.commands_processed}
└ 👥 Подписчиков: {len(self.notification_subscribers)}

<b>⏰ Последнее обновление:</b> {datetime.now().strftime('%H:%M:%S')}
"""
        return text
    
    # Обработчики команд
    async def cmd_start(self, message: Message, state: FSMContext):
        """Обработчик команды /start"""
        user_id = message.from_user.id
        user_name = message.from_user.full_name or "Неизвестный"
        
        logger.info(f"Команда /start от пользователя {user_name} (ID: {user_id})")
        self.commands_processed += 1
        
        if not self._is_authorized(user_id):
            await message.answer(
                "❌ <b>Доступ запрещен</b>\n\n"
                f"Ваш ID: <code>{user_id}</code>\n"
                "Обратитесь к администратору для получения доступа.",
                parse_mode="HTML"
            )
            return
        
        await state.set_state(UserStates.main_menu)
        
        # Получаем статистику
        monitoring_status = monitoring_service.get_status()
        
        welcome_text = f"""
<b>🤖 TurboShpalych Pro - Мониторинг турникетов</b>

Добро пожаловать, {message.from_user.first_name}! 👋

<b>📊 Система:</b>
├ 📡 Устройств: {len(monitoring_status.get('monitors', {}))}
├ 🔄 Мониторинг: {'🟢 Активен' if monitoring_status.get('is_running') else '🔴 Остановлен'}
├ ⏱️ Интервал: {monitoring_status.get('ping_interval', 30)}с
└ 👤 Ваш ID: <code>{user_id}</code>

Выберите действие:
"""
        
        await message.answer(
            welcome_text,
            parse_mode="HTML",
            reply_markup=self._create_main_keyboard()
        )
        self.messages_sent += 1
    
    async def cmd_help(self, message: Message):
        """Обработчик команды /help"""
        self.commands_processed += 1
        
        help_text = """
<b>ℹ️ Справка TurboShpalych Pro</b>

<b>📱 Основные команды:</b>
• /start - Главное меню
• /help - Эта справка
• /status - Быстрый статус
• /ping - Пинг всех устройств

<b>🎯 Возможности:</b>
• Мониторинг турникетов в реальном времени
• Автоматические уведомления о сбоях
• Детальная статистика и графики
• Управление категориями устройств
• Система мероприятий

<b>🔔 Уведомления:</b>
• Падение устройства
• Восстановление устройства
• Изменение статуса мониторинга
• Критические ошибки системы

<b>💡 Подсказки:</b>
• Используйте кнопки для навигации
• Подпишитесь на уведомления
• Проверяйте статистику регулярно

<b>🆔 Ваш ID:</b> <code>{message.from_user.id}</code>
"""
        
        await message.answer(help_text, parse_mode="HTML")
        self.messages_sent += 1
    
    async def cmd_status(self, message: Message):
        """Обработчик команды /status"""
        self.commands_processed += 1
        
        if not self._is_authorized(message.from_user.id):
            await message.answer("❌ Доступ запрещен")
            return
        
        monitoring_status = monitoring_service.get_status()
        stats_text = self._format_statistics(monitoring_status)
        
        await message.answer(stats_text, parse_mode="HTML")
        self.messages_sent += 1
    
    async def cmd_ping(self, message: Message):
        """Обработчик команды /ping"""
        self.commands_processed += 1
        
        if not self._is_authorized(message.from_user.id):
            await message.answer("❌ Доступ запрещен")
            return
        
        status_msg = await message.answer("🔄 <b>Выполняется пинг всех устройств...</b>", parse_mode="HTML")
        
        try:
            results = await monitoring_service.ping_all_now()
            
            online_count = sum(1 for r in results if r["status"] == "online")
            offline_count = len(results) - online_count
            
            result_text = f"""
<b>🎯 Результаты пинга</b>

<b>📊 Итого:</b>
├ 📡 Всего устройств: {len(results)}
├ 🟢 Онлайн: {online_count}
├ 🔴 Офлайн: {offline_count}
└ 📈 Доступность: {(online_count/len(results)*100):.1f}%

<b>⏰ Время выполнения:</b> {datetime.now().strftime('%H:%M:%S')}
"""
            
            await status_msg.edit_text(result_text, parse_mode="HTML")
            
        except Exception as e:
            await status_msg.edit_text(f"❌ <b>Ошибка выполнения пинга:</b> {e}", parse_mode="HTML")
        
        self.messages_sent += 1
    
    # Обработчики callback'ов
    async def handle_system_status(self, callback: CallbackQuery):
        """Показать статус системы"""
        await callback.answer("🔄 Загрузка статуса...")
        
        monitoring_status = monitoring_service.get_status()
        stats_text = self._format_statistics(monitoring_status)
        
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="system_status"))
        keyboard.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        
        await callback.message.edit_text(
            stats_text,
            parse_mode="HTML",
            reply_markup=keyboard.as_markup()
        )
    
    async def handle_all_devices(self, callback: CallbackQuery):
        """Показать все устройства"""
        await callback.answer("📋 Загрузка устройств...")
        
        monitoring_status = monitoring_service.get_status()
        monitors = monitoring_status.get("monitors", {})
        
        devices = []
        for device_id, monitor in monitors.items():
            devices.append({
                "device_id": device_id,
                "ip": monitor["ip"],
                "status": monitor["current_status"],
                "response_time": monitor["response_time"]
            })
        
        devices.sort(key=lambda x: x["device_id"])
        text = self._format_device_list(devices, "Все устройства")
        
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="all_devices"))
        keyboard.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard.as_markup()
        )
    
    async def handle_ping_now(self, callback: CallbackQuery):
        """Выполнить пинг сейчас"""
        await callback.answer("🎯 Запуск пинга...")
        
        await callback.message.edit_text("🔄 <b>Выполняется пинг всех устройств...</b>", parse_mode="HTML")
        
        try:
            results = await monitoring_service.ping_all_now()
            
            online_devices = [r for r in results if r["status"] == "online"]
            offline_devices = [r for r in results if r["status"] == "offline"]
            
            text = f"""
<b>🎯 Результаты пинга</b>

<b>📊 Сводка:</b>
├ 📡 Всего: {len(results)}
├ 🟢 Онлайн: {len(online_devices)}
├ 🔴 Офлайн: {len(offline_devices)}
└ 📈 Доступность: {(len(online_devices)/len(results)*100):.1f}%

<b>⏰ Выполнено:</b> {datetime.now().strftime('%H:%M:%S')}
"""
            
            keyboard = InlineKeyboardBuilder()
            keyboard.row(InlineKeyboardButton(text="📋 Подробности", callback_data="all_devices"))
            keyboard.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
            
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=keyboard.as_markup()
            )
            
        except Exception as e:
            await callback.message.edit_text(
                f"❌ <b>Ошибка выполнения пинга:</b> {e}",
                parse_mode="HTML"
            )
    
    async def handle_notifications(self, callback: CallbackQuery):
        """Управление уведомлениями"""
        user_id = callback.from_user.id
        is_subscribed = user_id in self.notification_subscribers
        
        if is_subscribed:
            self.notification_subscribers.discard(user_id)
            text = "🔕 <b>Уведомления отключены</b>\n\nВы больше не будете получать автоматические уведомления о статусе устройств."
            button_text = "🔔 Включить уведомления"
            callback_data = "notifications"
        else:
            self.notification_subscribers.add(user_id)
            text = "🔔 <b>Уведомления включены</b>\n\nВы будете получать уведомления о:\n• Падении устройств\n• Восстановлении устройств\n• Критических ошибках системы"
            button_text = "🔕 Отключить уведомления"
            callback_data = "notifications"
        
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text=button_text, callback_data=callback_data))
        keyboard.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        
        await callback.answer("✅ Настройки обновлены")
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard.as_markup()
        )
    
    async def handle_main_menu(self, callback: CallbackQuery, state: FSMContext):
        """Вернуться в главное меню"""
        await state.set_state(UserStates.main_menu)
        await callback.answer()
        
        monitoring_status = monitoring_service.get_status()
        
        text = f"""
<b>🤖 TurboShpalych Pro - Главное меню</b>

<b>📊 Система:</b>
├ 📡 Устройств: {len(monitoring_status.get('monitors', {}))}
├ 🔄 Мониторинг: {'🟢 Активен' if monitoring_status.get('is_running') else '🔴 Остановлен'}
└ ⏱️ Интервал: {monitoring_status.get('ping_interval', 30)}с

Выберите действие:
"""
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=self._create_main_keyboard()
        )
    
    def _register_handlers(self):
        """Регистрация обработчиков"""
        # Команды
        self.dp.message.register(self.cmd_start, CommandStart())
        self.dp.message.register(self.cmd_help, Command('help'))
        self.dp.message.register(self.cmd_status, Command('status'))
        self.dp.message.register(self.cmd_ping, Command('ping'))
        
        # Callback'и
        self.dp.callback_query.register(self.handle_main_menu, F.data == "main_menu")
        self.dp.callback_query.register(self.handle_system_status, F.data == "system_status")
        self.dp.callback_query.register(self.handle_all_devices, F.data == "all_devices")
        self.dp.callback_query.register(self.handle_ping_now, F.data == "ping_now")
        self.dp.callback_query.register(self.handle_notifications, F.data == "notifications")
    
    async def _handle_monitoring_events(self, event: Dict[str, Any]):
        """Обработчик событий мониторинга"""
        try:
            event_type = event.get("type")
            data = event.get("data", {})
            
            if event_type == "device_failure":
                device_id = data.get("device_id")
                ip = data.get("ip")
                message = f"""
🔴 <b>УСТРОЙСТВО НЕДОСТУПНО</b>

📍 <b>Устройство:</b> <code>{device_id}</code>
🌐 <b>IP:</b> <code>{ip}</code>
⏰ <b>Время:</b> {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}

❌ Устройство не отвечает на пинг
"""
                await self._send_to_subscribers(message)
                
            elif event_type == "device_recovery":
                device_id = data.get("device_id")
                ip = data.get("ip")
                response_time = data.get("response_time")
                
                response_info = f" ({response_time}ms)" if response_time else ""
                
                message = f"""
🟢 <b>УСТРОЙСТВО ВОССТАНОВЛЕНО</b>

📍 <b>Устройство:</b> <code>{device_id}</code>
🌐 <b>IP:</b> <code>{ip}</code>
⏰ <b>Время:</b> {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}
⚡ <b>Отклик:</b> {response_time}ms

✅ Устройство снова доступно{response_info}
"""
                await self._send_to_subscribers(message)
                
            elif event_type == "monitoring_started":
                devices_count = data.get("devices_count", 0)
                message = f"""
🚀 <b>МОНИТОРИНГ ЗАПУЩЕН</b>

📡 Начат мониторинг {devices_count} устройств
⏰ {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}

Система автоматически отслеживает состояние турникетов и отправляет уведомления при изменениях.
"""
                await self._send_to_subscribers(message)
                
            elif event_type == "monitoring_stopped":
                message = f"""
🛑 <b>МОНИТОРИНГ ОСТАНОВЛЕН</b>

⏰ {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}

Автоматический мониторинг устройств приостановлен.
"""
                await self._send_to_subscribers(message)
                
        except Exception as e:
            logger.error(f"Ошибка обработки события мониторинга: {e}")
    
    async def start(self):
        """Запустить бота"""
        if self.is_running:
            logger.warning("Бот уже запущен")
            return
        
        token = self.config.get("TOKEN")
        if not token:
            raise ValueError("Токен бота не настроен в config.json")
        
        self.bot = Bot(token=token)
        self.dp = Dispatcher(storage=MemoryStorage())
        
        # Регистрируем обработчики
        self._register_handlers()
        
        # Подписываемся на события мониторинга
        await event_manager.subscribe(self._handle_monitoring_events)
        
        self.is_running = True
        self.start_time = datetime.now()
        
        logger.info("🚀 Telegram бот запускается...")
        
        try:
            # Устанавливаем команды бота
            await self.bot.set_my_commands([
                types.BotCommand(command="start", description="Главное меню"),
                types.BotCommand(command="help", description="Справка"),
                types.BotCommand(command="status", description="Статус системы"),
                types.BotCommand(command="ping", description="Пинг всех устройств")
            ])
            
            # Отправляем уведомление о запуске
            await self._send_to_subscribers(f"""
🤖 <b>Бот TurboShpalych Pro запущен</b>

⏰ {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}

Бот готов к работе! Используйте /start для доступа к функциям.
""")
            
            # Запускаем polling
            await self.dp.start_polling(
                self.bot,
                allowed_updates=self.dp.resolve_used_update_types()
            )
            
        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")
            raise
        finally:
            await self.stop()
    
    async def stop(self):
        """Остановить бота"""
        if not self.is_running:
            return
        
        logger.info("🛑 Остановка Telegram бота...")
        
        self.is_running = False
        
        # Отписываемся от событий
        await event_manager.unsubscribe(self._handle_monitoring_events)
        
        # Закрываем сессию бота
        if self.bot:
            await self.bot.session.close()
        
        logger.info("✅ Telegram бот остановлен")
    
    def get_status(self) -> Dict[str, Any]:
        """Получить статус бота"""
        uptime = None
        if self.start_time:
            delta = datetime.now() - self.start_time
            uptime = str(delta).split('.')[0]  # Убираем микросекунды
        
        return {
            "is_running": self.is_running,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime": uptime,
            "messages_sent": self.messages_sent,
            "commands_processed": self.commands_processed,
            "authorized_users": len(self._get_authorized_chat_ids()),
            "notification_subscribers": len(self.notification_subscribers),
            "config_loaded": bool(self.config)
        }


# Глобальный экземпляр бота
telegram_bot_service = TelegramBotService()