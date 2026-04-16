from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.core.config import settings
from app.services.traje_iron_man.operaciones import (
    get_traje_status,
    monthly_due_window,
    run_traje_operation,
    should_run_monthly_archive,
)

logger = logging.getLogger(__name__)


class TrajeIronManMonthlyWorker:
    def __init__(self) -> None:
        self._poll_seconds = max(15, int(settings.traje_iron_man_scheduler_poll_seconds))
        self._default_lote = max(1, int(settings.traje_iron_man_default_lote))

    async def run_forever(self) -> None:
        logger.info(
            "Traje Iron Man worker enabled (poll_seconds=%s, default_lote=%s)",
            self._poll_seconds,
            self._default_lote,
        )
        while True:
            try:
                self._tick()
            except Exception:
                logger.exception("Traje Iron Man worker tick failed")
            await asyncio.sleep(self._poll_seconds)

    def _tick(self) -> None:
        now = datetime.now().astimezone()
        status = get_traje_status()
        last_operation = status.get("last_operation")
        if not isinstance(last_operation, dict):
            last_operation = None
        if not should_run_monthly_archive(now, last_operation):
            return
        window_start, window_end = monthly_due_window(now)
        if not (window_start <= now <= window_end):
            return
        logger.info("Traje Iron Man monthly window reached, executing automatic archive")
        run_traje_operation(
            operacion="archivar",
            lote=self._default_lote,
            dry_run=False,
            trigger="scheduler",
        )
