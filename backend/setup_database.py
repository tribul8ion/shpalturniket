#!/usr/bin/env python3
"""
Скрипт для настройки и инициализации базы данных
"""

import sys
import logging
from pathlib import Path

# Добавляем путь к приложению
sys.path.append(str(Path(__file__).parent))

from app.core.db import create_db_and_tables, get_session
from app.models.device import Device
from app.models.event import EventCategory, EventDevice
from sqlmodel import Session, select
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_database():
    """Настроить базу данных"""
    logger.info("🔧 Настройка базы данных...")
    
    # Создаем таблицы
    create_db_and_tables()
    logger.info("✅ Таблицы созданы")
    
    # Инициализируем данные из конфигурации
    init_devices_from_config()
    logger.info("✅ База данных настроена")

def init_devices_from_config():
    """Инициализировать устройства из IP_list.json"""
    try:
        BASE_DIR = Path(__file__).parent.parent
        ip_list_path = BASE_DIR / "IP_list.json"
        
        if not ip_list_path.exists():
            logger.warning("⚠️ IP_list.json не найден, пропускаем инициализацию")
            return
        
        with open(ip_list_path, 'r', encoding='utf-8') as f:
            ip_data = json.load(f)
        
        with next(get_session()) as session:
            for device_id, device_info in ip_data.items():
                if isinstance(device_info, list) and len(device_info) >= 2:
                    # Проверяем, существует ли устройство
                    existing = session.exec(
                        select(Device).where(Device.device_id == device_id)
                    ).first()
                    
                    if not existing:
                        # Создаем новое устройство
                        device = Device(
                            device_id=device_id,
                            ip=device_info[0],
                            description=device_info[1],
                            category="Турникет",
                            status="unknown"
                        )
                        session.add(device)
                        logger.info(f"➕ Добавлено устройство: {device_id}")
            
            session.commit()
            
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации устройств: {e}")

def create_sample_category():
    """Создать примерную категорию мероприятия"""
    try:
        with next(get_session()) as session:
            # Проверяем, есть ли уже категории
            existing = session.exec(select(EventCategory)).first()
            if existing:
                logger.info("📋 Категории уже существуют")
                return
            
            # Создаем тестовую категорию
            category = EventCategory(
                name="Тестовое мероприятие",
                description="Пример категории для демонстрации функционала",
                is_active=True
            )
            session.add(category)
            session.commit()
            session.refresh(category)
            
            logger.info(f"📋 Создана тестовая категория: {category.name}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания категории: {e}")

def check_database():
    """Проверить состояние базы данных"""
    logger.info("🔍 Проверка базы данных...")
    
    try:
        with next(get_session()) as session:
            # Проверяем устройства
            devices = session.exec(select(Device)).all()
            logger.info(f"📱 Устройств в базе: {len(devices)}")
            
            # Проверяем категории
            categories = session.exec(select(EventCategory)).all()
            logger.info(f"📋 Категорий в базе: {len(categories)}")
            
            # Проверяем связи
            event_devices = session.exec(select(EventDevice)).all()
            logger.info(f"🔗 Связей устройств с категориями: {len(event_devices)}")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка проверки базы данных: {e}")
        return False

def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Настройка базы данных')
    parser.add_argument('--init', action='store_true', help='Инициализировать базу данных')
    parser.add_argument('--check', action='store_true', help='Проверить базу данных')
    parser.add_argument('--sample', action='store_true', help='Создать примерные данные')
    
    args = parser.parse_args()
    
    if args.check:
        if check_database():
            print("✅ База данных в порядке")
            return 0
        else:
            print("❌ Проблемы с базой данных")
            return 1
    
    if args.init:
        setup_database()
        print("✅ База данных инициализирована")
    
    if args.sample:
        create_sample_category()
        print("✅ Примерные данные созданы")
    
    if not any([args.init, args.check, args.sample]):
        # По умолчанию инициализируем базу
        setup_database()
        create_sample_category()
        check_database()
        print("✅ Настройка завершена")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())