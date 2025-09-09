#!/usr/bin/env python3
"""
Скрипт для запуска полной системы мониторинга турникетов
Запускает backend, frontend и опционально Telegram бота
"""

import asyncio
import subprocess
import sys
import os
import signal
import time
import json
import logging
from pathlib import Path
from typing import List, Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('system.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class SystemManager:
    """Менеджер для управления всей системой"""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.processes: List[subprocess.Popen] = []
        self.running = False
        
    def check_dependencies(self) -> bool:
        """Проверить наличие необходимых зависимостей"""
        logger.info("🔍 Проверка зависимостей...")
        
        # Проверяем Python зависимости
        try:
            import fastapi
            import uvicorn
            import sqlmodel
            import icmplib
            import aiogram
            logger.info("✅ Python зависимости найдены")
        except ImportError as e:
            logger.error(f"❌ Отсутствует Python зависимость: {e}")
            logger.error("💡 Установите зависимости: pip install -r backend/requirements.txt")
            return False
        
        # Проверяем Node.js зависимости
        frontend_dir = self.base_dir / "frontend"
        node_modules = frontend_dir / "node_modules"
        
        if not node_modules.exists():
            logger.error("❌ Frontend зависимости не установлены")
            logger.error("💡 Перейдите в папку frontend и выполните: npm install")
            return False
        
        logger.info("✅ Node.js зависимости найдены")
        
        # Проверяем конфигурационные файлы
        config_files = [
            self.base_dir / "IP_list.json",
            self.base_dir / "config.json"
        ]
        
        for config_file in config_files:
            if not config_file.exists():
                logger.warning(f"⚠️ Конфигурационный файл не найден: {config_file}")
                self.create_default_config(config_file)
        
        return True
    
    def create_default_config(self, config_file: Path):
        """Создать конфигурационный файл по умолчанию"""
        logger.info(f"📝 Создание конфигурации по умолчанию: {config_file.name}")
        
        if config_file.name == "IP_list.json":
            default_config = {
                "DEVICE001": ["192.168.1.100", "Турникет 1 - Главный вход", "1"],
                "DEVICE002": ["192.168.1.101", "Турникет 2 - Боковой вход", "1"],
                "DEVICE003": ["192.168.1.102", "Турникет 3 - Аварийный выход", "1"]
            }
        elif config_file.name == "config.json":
            default_config = {
                "TOKEN": "YOUR_TELEGRAM_BOT_TOKEN_HERE",
                "time_connect": "30",
                "chat_id": []
            }
        else:
            return
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Создан файл {config_file.name}")
    
    def start_backend(self) -> Optional[subprocess.Popen]:
        """Запустить backend сервер"""
        logger.info("🚀 Запуск backend сервера...")
        
        try:
            backend_dir = self.base_dir / "backend"
            
            # Проверяем наличие main.py
            main_file = backend_dir / "app" / "main.py"
            if not main_file.exists():
                logger.error(f"❌ Файл {main_file} не найден")
                return None
            
            # Запускаем uvicorn
            process = subprocess.Popen([
                sys.executable, "-m", "uvicorn", 
                "app.main:app",
                "--host", "127.0.0.1",
                "--port", "8000",
                "--reload"
            ], 
            cwd=backend_dir,
            env={**os.environ, 'PYTHONPATH': str(backend_dir)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
            )
            
            # Ждем немного и проверяем, что процесс запустился
            time.sleep(2)
            if process.poll() is None:
                logger.info("✅ Backend сервер запущен на http://127.0.0.1:8000")
                logger.info("📚 API документация: http://127.0.0.1:8000/api/docs")
                return process
            else:
                stdout, stderr = process.communicate()
                logger.error(f"❌ Backend сервер не запустился")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка запуска backend: {e}")
            return None
    
    def start_frontend(self) -> Optional[subprocess.Popen]:
        """Запустить frontend сервер"""
        logger.info("🎨 Запуск frontend сервера...")
        
        try:
            frontend_dir = self.base_dir / "frontend"
            
            # Проверяем наличие package.json
            package_json = frontend_dir / "package.json"
            if not package_json.exists():
                logger.error(f"❌ Файл {package_json} не найден")
                return None
            
            # Запускаем npm run dev
            process = subprocess.Popen([
                "npm", "run", "dev"
            ], 
            cwd=frontend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
            )
            
            # Ждем немного и проверяем, что процесс запустился
            time.sleep(3)
            if process.poll() is None:
                logger.info("✅ Frontend сервер запущен на http://localhost:5173")
                return process
            else:
                stdout, stderr = process.communicate()
                logger.error(f"❌ Frontend сервер не запустился")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка запуска frontend: {e}")
            return None
    
    def start_telegram_bot(self) -> Optional[subprocess.Popen]:
        """Запустить Telegram бота (опционально)"""
        logger.info("🤖 Запуск Telegram бота...")
        
        # Проверяем конфигурацию бота
        config_file = self.base_dir / "config.json"
        if not config_file.exists():
            logger.warning("⚠️ Конфигурация бота не найдена, пропускаем запуск")
            return None
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            token = config.get("TOKEN", "")
            if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
                logger.warning("⚠️ Токен Telegram бота не настроен, пропускаем запуск")
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка чтения конфигурации бота: {e}")
            return None
        
        try:
            bot_file = self.base_dir / "advanced_bot.py"
            if not bot_file.exists():
                logger.warning("⚠️ Файл advanced_bot.py не найден, пропускаем запуск")
                return None
            
            # Запускаем бота
            process = subprocess.Popen([
                sys.executable, str(bot_file)
            ], 
            cwd=self.base_dir,
            env={**os.environ, 'PYTHONPATH': str(self.base_dir)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
            )
            
            # Ждем немного и проверяем, что процесс запустился
            time.sleep(2)
            if process.poll() is None:
                logger.info("✅ Telegram бот запущен")
                return process
            else:
                stdout, stderr = process.communicate()
                logger.error(f"❌ Telegram бот не запустился")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Telegram бота: {e}")
            return None
    
    def start_system(self, include_bot: bool = True):
        """Запустить всю систему"""
        logger.info("🚀 Запуск системы мониторинга турникетов...")
        
        # Проверяем зависимости
        if not self.check_dependencies():
            logger.error("❌ Не удалось запустить систему из-за отсутствующих зависимостей")
            return False
        
        self.running = True
        
        # Запускаем backend
        backend_process = self.start_backend()
        if backend_process:
            self.processes.append(backend_process)
        else:
            logger.error("❌ Критическая ошибка: не удалось запустить backend")
            return False
        
        # Ждем, чтобы backend полностью загрузился
        time.sleep(3)
        
        # Запускаем frontend
        frontend_process = self.start_frontend()
        if frontend_process:
            self.processes.append(frontend_process)
        else:
            logger.warning("⚠️ Frontend не запустился, но система может работать")
        
        # Запускаем Telegram бота (опционально)
        if include_bot:
            bot_process = self.start_telegram_bot()
            if bot_process:
                self.processes.append(bot_process)
        
        logger.info("🎉 Система запущена!")
        logger.info("🌐 Веб-интерфейс: http://localhost:5173")
        logger.info("🔧 API: http://127.0.0.1:8000/api/docs")
        logger.info("📊 Мониторинг запустится автоматически")
        
        return True
    
    def stop_system(self):
        """Остановить всю систему"""
        logger.info("🛑 Остановка системы...")
        
        self.running = False
        
        for process in self.processes:
            try:
                process.terminate()
                # Ждем завершения
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            except Exception as e:
                logger.error(f"Ошибка остановки процесса: {e}")
        
        self.processes.clear()
        logger.info("✅ Система остановлена")
    
    def monitor_processes(self):
        """Мониторинг запущенных процессов"""
        while self.running:
            try:
                for i, process in enumerate(self.processes[:]):
                    if process.poll() is not None:
                        logger.warning(f"⚠️ Процесс {i} завершился неожиданно")
                        self.processes.remove(process)
                
                time.sleep(5)
            except KeyboardInterrupt:
                break
    
    def run(self, include_bot: bool = True):
        """Запустить систему и ждать сигнала остановки"""
        def signal_handler(signum, frame):
            logger.info(f"📡 Получен сигнал {signum}, останавливаем систему...")
            self.stop_system()
            sys.exit(0)
        
        # Регистрируем обработчики сигналов
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            if self.start_system(include_bot):
                logger.info("✨ Система работает. Нажмите Ctrl+C для остановки.")
                self.monitor_processes()
            else:
                logger.error("❌ Не удалось запустить систему")
                return False
        except KeyboardInterrupt:
            logger.info("📡 Получен сигнал прерывания...")
        finally:
            self.stop_system()
        
        return True


def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Система мониторинга турникетов')
    parser.add_argument('--no-bot', action='store_true', help='Не запускать Telegram бота')
    parser.add_argument('--check-deps', action='store_true', help='Только проверить зависимости')
    
    args = parser.parse_args()
    
    manager = SystemManager()
    
    if args.check_deps:
        if manager.check_dependencies():
            print("✅ Все зависимости установлены")
            return 0
        else:
            print("❌ Некоторые зависимости отсутствуют")
            return 1
    
    include_bot = not args.no_bot
    
    if manager.run(include_bot):
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())