from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx

from .models import RoutingTask


class BenchmarkClient:
    def __init__(self):
        self.task_api_url = os.getenv("SLUICE_TASK_API", "").strip().rstrip("/")
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
        self._local_tasks = self._load_local_tasks()
        self._cursor = 0

    def _load_local_tasks(self) -> list[RoutingTask]:
        task_path = Path(__file__).resolve().parent / "benchmarks" / "tasks.json"
        payload = json.loads(task_path.read_text(encoding="utf-8"))
        return [RoutingTask.model_validate(item) for item in payload]

    async def _get_with_retry(self, url: str, retries: int = 3):
        for attempt in range(retries):
            try:
                response = await self.client.get(url)
                response.raise_for_status()
                return response
            except httpx.ReadTimeout:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(2**attempt)

    async def fetch_random_task(self) -> RoutingTask:
        if self.task_api_url:
            response = await self._get_with_retry(f"{self.task_api_url}/random")
            return RoutingTask.model_validate(response.json())

        task = self._local_tasks[self._cursor % len(self._local_tasks)]
        self._cursor += 1
        return task.model_copy(deep=True)

    async def fetch_all_tasks(self) -> list[RoutingTask]:
        if self.task_api_url:
            response = await self._get_with_retry(f"{self.task_api_url}/all")
            return [RoutingTask.model_validate(item) for item in response.json()]
        return [task.model_copy(deep=True) for task in self._local_tasks]

    async def close(self):
        await self.client.aclose()
