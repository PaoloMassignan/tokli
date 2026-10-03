"""The current service snapshot, swapped atomically on a configuration change (CF-005,
API-007; ADR 0009). A request reads ``current()`` once and keeps that snapshot to its end."""

from __future__ import annotations

import threading

from tokli.app.bootstrap import Services, rebuild
from tokli.config import EffectiveConfig


class Runtime:
    def __init__(self, services: Services) -> None:
        self._services = services
        self._lock = threading.Lock()

    def current(self) -> Services:
        with self._lock:
            return self._services

    def swap(self, config: EffectiveConfig) -> Services:
        """Builds services for ``config`` and makes them current for subsequent requests."""
        with self._lock:
            self._services = rebuild(self._services, config)
            return self._services
