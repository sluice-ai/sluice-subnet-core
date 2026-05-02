import pytest

from sluice.benchmark_client import BenchmarkClient


@pytest.mark.asyncio
async def test_benchmark_client_uses_local_fallback_tasks():
    client = BenchmarkClient()

    tasks = await client.fetch_all_tasks()
    assert len(tasks) >= 4

    first = await client.fetch_random_task()
    second = await client.fetch_random_task()

    assert first.task_id != second.task_id

    await client.close()
