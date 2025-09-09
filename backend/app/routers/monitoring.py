"""
Router для управления мониторингом
"""

from fastapi import APIRouter, HTTPException
from ..services.monitoring import monitoring_service

router = APIRouter()


@router.get("/monitoring/status", summary="Получить статус мониторинга")
async def get_monitoring_status():
    """Получить статус сервиса мониторинга"""
    return monitoring_service.get_status()


@router.post("/monitoring/start", summary="Запустить мониторинг")
async def start_monitoring():
    """Запустить автоматический мониторинг устройств"""
    try:
        await monitoring_service.start()
        return {"message": "Мониторинг запущен успешно", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка запуска мониторинга: {e}")


@router.post("/monitoring/stop", summary="Остановить мониторинг")
async def stop_monitoring():
    """Остановить автоматический мониторинг устройств"""
    try:
        await monitoring_service.stop()
        return {"message": "Мониторинг остановлен успешно", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка остановки мониторинга: {e}")


@router.post("/monitoring/ping-now", summary="Выполнить немедленный пинг")
async def ping_all_now():
    """Выполнить немедленный пинг всех устройств"""
    try:
        results = await monitoring_service.ping_all_now()
        return {
            "results": results,
            "total_devices": len(results),
            "online_count": sum(1 for r in results if r["status"] == "online"),
            "offline_count": sum(1 for r in results if r["status"] == "offline"),
            "success": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка выполнения пинга: {e}")


@router.post("/monitoring/reload-config", summary="Перезагрузить конфигурацию")
async def reload_monitoring_config():
    """Перезагрузить конфигурацию устройств"""
    try:
        await monitoring_service._reload_configuration()
        return {"message": "Конфигурация перезагружена успешно", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка перезагрузки конфигурации: {e}")