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
from .core.db import create_db_and_tables
from .utils.monitor import monitoring_service


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
def on_startup():
    create_db_and_tables()
    # Читаем интервал из config.json, если есть
    try:
        import json
        from pathlib import Path
        BASE_DIR = Path(__file__).parent.parent
        cfg_path = BASE_DIR / "config.json"
        interval = 30
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                interval = int(cfg.get("time_connect", interval))
        monitoring_service.interval_seconds = max(5, int(interval))
    except Exception:
        pass
    try:
        monitoring_service.start()
    except Exception as e:
        print(f"Failed to start monitoring service: {e}")


if __name__ == "__main__":
    try:
        import uvicorn

        uvicorn.run("app.main:app", host="127.0.0.1", port=int(settings["PORT"]), reload=False)
    except Exception as e:
        print(f"Failed to start uvicorn: {e}")
