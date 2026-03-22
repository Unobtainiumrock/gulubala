"""Tests for telephony/presenter_gather coordination."""

from __future__ import annotations

import asyncio

import pytest

from telephony import presenter_gather


@pytest.fixture(autouse=True)
def _clear_pending() -> None:
    with presenter_gather._lock:
        presenter_gather._pending.clear()
    yield
    with presenter_gather._lock:
        presenter_gather._pending.clear()


def test_resolve_gather_ignores_cancelled_future() -> None:
    async def _run() -> None:
        loop = asyncio.get_running_loop()
        fut = presenter_gather.create_gather_future("s1", "f1", loop)
        presenter_gather.cancel_gather("s1", "f1")
        await asyncio.sleep(0)
        assert fut.cancelled()
        assert presenter_gather.resolve_gather("s1", "f1", "late") is False

    asyncio.run(_run())


def test_resolve_gather_succeeds_when_pending() -> None:
    async def _run() -> None:
        loop = asyncio.get_running_loop()
        fut = presenter_gather.create_gather_future("s2", "f2", loop)
        assert presenter_gather.resolve_gather("s2", "f2", "value") is True
        await asyncio.sleep(0)
        assert fut.result() == "value"

    asyncio.run(_run())


def test_cancel_gather_removes_pending() -> None:
    async def _run() -> None:
        loop = asyncio.get_running_loop()
        presenter_gather.create_gather_future("s3", "f3", loop)
        presenter_gather.cancel_gather("s3", "f3")
        await asyncio.sleep(0)
        assert presenter_gather.resolve_gather("s3", "f3", "x") is False

    asyncio.run(_run())
