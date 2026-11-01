"""Backup-task operations for the UniFi Drive API client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .api_errors import InvalidAuth, UnexpectedResponse, UnsupportedFeature
from .security import safe_response_summary

_LOGGER = logging.getLogger(__name__)

BACKUP_NOT_FOUND_HTTP_STATUSES = {404, 405}
BACKUP_TASKS_PATH = "/proxy/drive/api/v2/remote-backup/tasks"
BACKUP_TASK_RUN_PATH = "/proxy/drive/api/v2/remote-backup/run-task/{task_id}"


class ApiBackupMixin:
    """Backup behavior split from the main API client class."""

    _authenticated: bool
    _backup_tasks_read_supported: bool | None

    if TYPE_CHECKING:
        async def _ensure_authenticated(self) -> None: ...
        async def async_login(self) -> None: ...
        async def _request_raw(
            self,
            method: str,
            path: str,
            *,
            json_body: dict[str, Any] | None = None,
        ) -> tuple[int, Any]: ...

    @property
    def backup_tasks_read_supported(self) -> bool | None:
        """Return whether the backup-task read endpoint is known to be supported."""
        return self._backup_tasks_read_supported

    async def async_get_backup_tasks(self) -> list[dict[str, Any]]:
        """Return known remote-backup tasks if the endpoint is available."""
        await self._ensure_authenticated()
        try:
            return await self._async_get_backup_tasks_once()
        except InvalidAuth:
            _LOGGER.debug("UNAS session expired before backup-task read; retrying login once")
            self._authenticated = False
            await self.async_login()
            return await self._async_get_backup_tasks_once()

    async def async_run_backup_task(self, task_id: str) -> None:
        """Trigger execution of a remote-backup task."""
        task_id = str(task_id).strip()
        if not task_id:
            raise UnexpectedResponse("Backup task id is empty")

        await self._ensure_authenticated()
        try:
            await self._async_run_backup_task_once(task_id)
        except InvalidAuth:
            _LOGGER.debug("UNAS session expired before backup-task run; retrying login once")
            self._authenticated = False
            await self.async_login()
            await self._async_run_backup_task_once(task_id)

    async def _async_get_backup_tasks_once(self) -> list[dict[str, Any]]:
        """Read backup tasks from the configured endpoint."""
        if self._backup_tasks_read_supported is False:
            return []

        status, payload = await self._request_raw("GET", BACKUP_TASKS_PATH)
        if status in BACKUP_NOT_FOUND_HTTP_STATUSES:
            self._backup_tasks_read_supported = False
            return []
        if status < 200 or status >= 300:
            _LOGGER.debug(
                "Backup-task endpoint %s returned HTTP %s", BACKUP_TASKS_PATH, status
            )
            return []

        tasks = self._extract_backup_tasks(payload)
        self._backup_tasks_read_supported = True
        return tasks

    async def _async_run_backup_task_once(self, task_id: str) -> None:
        """Trigger a backup task through the configured endpoint."""
        path = BACKUP_TASK_RUN_PATH.format(task_id=task_id)
        status, payload = await self._request_raw("POST", path, json_body={})
        if 200 <= status < 300:
            if isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, str) and data.strip().upper() not in {
                    "OK",
                    "QUEUED",
                    "STARTED",
                }:
                    _LOGGER.debug(
                        "Backup task returned unexpected payload data=%s",
                        safe_response_summary(data),
                    )
            return

        if status in BACKUP_NOT_FOUND_HTTP_STATUSES:
            raise UnsupportedFeature(
                "Remote-backup task endpoint is not available on this system."
            )
        raise UnsupportedFeature(
            f"Remote-backup task endpoint returned HTTP {status}: "
            f"{safe_response_summary(payload)}"
        )

    @staticmethod
    def _extract_backup_tasks(payload: Any) -> list[dict[str, Any]]:
        """Extract normalized backup-task items from endpoint payload."""
        tasks_payload: Any = payload
        if isinstance(payload, dict):
            for key in ("tasks", "data", "result", "results", "items"):
                if key in payload:
                    tasks_payload = payload[key]
                    break

        if not isinstance(tasks_payload, list):
            return []

        normalized: list[dict[str, Any]] = []
        for index, task in enumerate(tasks_payload):
            if not isinstance(task, dict):
                continue

            task_id = (
                task.get("id")
                or task.get("_id")
                or task.get("taskId")
                or task.get("task_id")
                or task.get("uuid")
            )
            if task_id in (None, ""):
                task_id = f"task_{index + 1}"

            name = (
                task.get("name")
                or task.get("taskName")
                or task.get("task_name")
                or task.get("title")
            )
            if name in (None, ""):
                name = f"Backup Task {index + 1}"

            normalized.append(
                {
                    "id": str(task_id),
                    "name": str(name),
                    "raw": task,
                }
            )

        return normalized
