"""
Фоновый сервис мониторинга устройств: периодический пинг, детект изменений статусов,
публикация в SSE и отправка уведомлений в Telegram.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import json

from sqlmodel import Session, select

from ..core.db import engine
from ..models.device import Device
from ..models.log import DeviceStatusLog
from .events_bus import event_manager
from .notifier import notifier


class MonitoringService:
    def __init__(self, interval_seconds: int = 30) -> None:
        self.interval_seconds = max(5, int(interval_seconds))
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()
        self._last_status_by_device: Dict[str, str] = {}

    def _load_config_devices(self) -> List[Tuple[str, str, str, bool]]:
        """Загрузка устройств из IP_list.json: returns list of (device_id, ip, description, enabled)."""
        base_dir = Path(__file__).parent.parent.parent
        ip_list_path = base_dir / "IP_list.json"
        devices: List[Tuple[str, str, str, bool]] = []
        if ip_list_path.exists():
            try:
                with open(ip_list_path, "r", encoding="utf-8") as f:
                    ip_data = json.load(f)
                for device_id, info in ip_data.items():
                    if isinstance(info, list) and len(info) >= 3:
                        ip = str(info[0])
                        descr = str(info[1])
                        enabled = bool(int(info[2]))
                        devices.append((device_id, ip, descr, enabled))
            except Exception:
                pass
        return devices

    async def _ping_ip(self, ip_address: str, count: int = 1, timeout: int = 2) -> Tuple[bool, int | None]:
        from icmplib import ping as icmp_ping
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: icmp_ping(ip_address, count=count, timeout=timeout))
            is_alive = getattr(result, 'is_alive', False)
            avg_rtt = getattr(result, 'avg_rtt', None)
            ms = int(avg_rtt * 1000) if avg_rtt is not None else None
            return is_alive, ms
        except Exception:
            return False, None

    async def _check_once(self) -> None:
        config_devices = [d for d in self._load_config_devices() if d[3]]  # only enabled
        # Fallback: also include DB devices if DB has entries not present in config
        with Session(engine) as session:
            db_devices: List[Device] = session.exec(select(Device)).all()
            db_lookup = {d.device_id: d for d in db_devices}
        for dev in db_devices:
            if dev.device_id not in {x[0] for x in config_devices}:
                config_devices.append((dev.device_id, dev.ip, dev.description or dev.device_id, True))

        # Ping concurrently
        tasks = [self._ping_ip(ip) for _, ip, _, _ in config_devices]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        now = datetime.utcnow()

        # Persist and emit
        with Session(engine) as session:
            for (device_id, ip, description, _), (alive, ms) in zip(config_devices, results):
                status = "online" if alive else "offline"
                # Detect status change
                prev = self._last_status_by_device.get(device_id)
                status_changed = prev is not None and prev != status
                self._last_status_by_device[device_id] = status

                # Update DB device if exists
                db_device = session.exec(select(Device).where(Device.device_id == device_id)).first()
                if db_device:
                    db_device.status = status
                    db_device.response_ms = ms
                    db_device.last_check = now
                    session.add(db_device)

                # Save log
                log = DeviceStatusLog(
                    device_id=device_id,
                    ip=ip,
                    status=status,
                    response_ms=ms,
                    category="Турникет",
                    created_at=now,
                )
                session.add(log)

                # Emit SSE
                payload = {
                    "device_id": device_id,
                    "ip": ip,
                    "status": status,
                    "response_time": ms,
                    "timestamp": now.isoformat(),
                }
                await event_manager.publish({
                    "type": "device_status",
                    "timestamp": now.isoformat(),
                    "data": payload,
                })

                # Telegram notifications on changes
                if status_changed:
                    emoji = "🟢" if status == "online" else "🔴"
                    text = (
                        f"{emoji} <b>Изменение статуса устройства</b>\n\n"
                        f"📍 Устройство: <b>{device_id}</b>\n"
                        f"🌐 IP: <code>{ip}</code>\n"
                        f"📊 Статус: <b>{'ОНЛАЙН' if status=='online' else 'ОФЛАЙН'}</b>\n"
                        f"⏱️ Время: {now.strftime('%d.%m.%Y %H:%M:%S')}"
                    )
                    await notifier.send_message(text)

            session.commit()

    async def _run(self) -> None:
        try:
            while not self._stopped.is_set():
                await self._check_once()
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_seconds)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if not self._task:
            return
        self._stopped.set()
        self._task.cancel()
        try:
            await self._task
        except Exception:
            pass
        finally:
            self._task = None


monitoring_service = MonitoringService()

