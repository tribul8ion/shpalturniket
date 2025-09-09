from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .routers import health
from .routers import devices
from .routers import ping
from .routers import themes
from .routers import events
from .routers import config
from .routers import bot
from .routers import events_api
from .routers import monitoring
from .core.db import create_db_and_tables
from .services.monitoring import monitoring_service
from .services.event_categories import event_category_service


def create_app() -> FastAPI:
    app = FastAPI(title=settings["APP_NAME"], version=settings["VERSION"], docs_url=f"{settings['API_PREFIX']}/docs", redoc_url=None)

    # CORS для локального фронтенда/tauri
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:5180",
            "http://127.0.0.1:5180",
            "http://localhost:5181",
            "http://127.0.0.1:5181",
            "tauri://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    # Routers
    app.include_router(health.router, prefix=settings["API_PREFIX"])
    app.include_router(devices.router, prefix=settings["API_PREFIX"])
    app.include_router(ping.router, prefix=settings["API_PREFIX"])
    app.include_router(themes.router, prefix=settings["API_PREFIX"])
    app.include_router(events.router, prefix=settings["API_PREFIX"])
    app.include_router(config.router, prefix=settings["API_PREFIX"])
    app.include_router(bot.router, prefix=f"{settings['API_PREFIX']}/bot")
    app.include_router(events_api.router, prefix=f"{settings['API_PREFIX']}/events")
    app.include_router(monitoring.router, prefix=settings["API_PREFIX"])

    @app.get("/")
    async def root():
        return {
            "name": settings["APP_NAME"],
            "version": settings["VERSION"],
            "api_prefix": settings["API_PREFIX"],
            "status": "ok",
        }

    return app


app = create_app()


@app.on_event("startup")
async def on_startup():
    create_db_and_tables()
    
    # Автоматически запускаем мониторинг при старте приложения
    try:
        await monitoring_service.start()
        print("🚀 Автоматический мониторинг турникетов запущен")
    except Exception as e:
        print(f"⚠️ Ошибка запуска мониторинга: {e}")
    
    # Инициализируем активные категории мероприятий
    try:
        await event_category_service.initialize_active_categories()
        print("📋 Активные категории мероприятий инициализированы")
    except Exception as e:
        print(f"⚠️ Ошибка инициализации категорий: {e}")

@app.on_event("shutdown")
async def on_shutdown():
    # Останавливаем мониторинг при завершении приложения
    try:
        await monitoring_service.stop()
        print("🛑 Мониторинг турникетов остановлен")
    except Exception as e:
        print(f"⚠️ Ошибка остановки мониторинга: {e}")


if __name__ == "__main__":
    try:
        import uvicorn

        uvicorn.run("app.main:app", host="127.0.0.1", port=int(settings["PORT"]), reload=False)
    except Exception as e:
        print(f"Failed to start uvicorn: {e}")
