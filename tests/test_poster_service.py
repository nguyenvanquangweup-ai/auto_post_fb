import asyncio
import threading
import time

from src.config import Group
from src.poster import PosterConfig, PosterService, ResultStatus


class FakeLogger:
    def info(self, msg):
        pass

    def error(self, msg):
        pass

    def warning(self, msg):
        pass

    def exception(self, msg):
        pass

    def log(self, level, msg):
        pass


def make_service(run_group_results, csv_calls):
    async def fake_run_group(page, group, content_template, images):
        return run_group_results.pop(0)

    config = PosterConfig(min_delay=0.0, max_delay=0.0, verify_feed=False)

    def csv_writer(group_name, status, message):
        csv_calls.append((group_name, status, message))

    return PosterService(config, FakeLogger(), csv_writer, run_group_fn=fake_run_group)


def test_run_requeues_failed_group_to_end_and_gives_up_after_two_attempts():
    groups = [Group("A", "urlA"), Group("B", "urlB")]
    results = [
        (ResultStatus.FAILED, "boom"),
        (ResultStatus.SUCCESS, "ok"),
        (ResultStatus.FAILED, "boom2"),
    ]
    csv_calls = []
    service = make_service(results, csv_calls)
    stop_event = threading.Event()

    asyncio.run(service.run(None, groups, "content", [], stop_event))

    assert csv_calls == [
        ("B", "SUCCESS", "ok"),
        ("A", "FAILED", "boom2"),
    ]


def test_run_stops_immediately_when_stop_event_already_set():
    groups = [Group("A", "urlA")]
    csv_calls = []
    service = make_service([], csv_calls)
    stop_event = threading.Event()
    stop_event.set()

    asyncio.run(service.run(None, groups, "content", [], stop_event))

    assert csv_calls == []


async def test_run_cancels_in_progress_group_when_stopped_mid_flight():
    groups = [Group("A", "urlA")]
    csv_calls = []

    async def fake_run_group(page, group, content_template, images):
        await asyncio.sleep(10)
        return (ResultStatus.SUCCESS, "ok")

    config = PosterConfig(min_delay=0.0, max_delay=0.0, verify_feed=False)

    def csv_writer(group_name, status, message):
        csv_calls.append((group_name, status, message))

    service = PosterService(config, FakeLogger(), csv_writer, run_group_fn=fake_run_group)
    stop_event = threading.Event()

    async def stop_soon():
        await asyncio.sleep(0.05)
        stop_event.set()

    start = time.monotonic()
    await asyncio.wait_for(
        asyncio.gather(service.run(None, groups, "content", [], stop_event), stop_soon()),
        timeout=2,
    )
    elapsed = time.monotonic() - start

    assert elapsed < 1
    assert csv_calls == []


def test_run_interrupts_inter_group_delay_when_stopped():
    groups = [Group("A", "urlA"), Group("B", "urlB")]
    results = [(ResultStatus.SUCCESS, "ok")]
    csv_calls = []

    async def fake_run_group(page, group, content_template, images):
        result = results.pop(0)
        stop_event.set()
        return result

    config = PosterConfig(min_delay=100.0, max_delay=100.0, verify_feed=False)

    def csv_writer(group_name, status, message):
        csv_calls.append((group_name, status, message))

    service = PosterService(config, FakeLogger(), csv_writer, run_group_fn=fake_run_group)
    stop_event = threading.Event()

    start = time.monotonic()
    asyncio.run(service.run(None, groups, "content", [], stop_event))
    elapsed = time.monotonic() - start

    assert elapsed < 2
    assert csv_calls == [("A", "SUCCESS", "ok")]


def test_run_isolates_non_poster_error_to_one_group_and_continues():
    groups = [Group("A", "urlA"), Group("B", "urlB")]
    csv_calls = []

    async def fake_run_group(page, group, content_template, images):
        if group.name == "A":
            raise Exception("boom")
        return (ResultStatus.SUCCESS, "ok")

    config = PosterConfig(min_delay=0.0, max_delay=0.0, verify_feed=False)

    def csv_writer(group_name, status, message):
        csv_calls.append((group_name, status, message))

    service = PosterService(config, FakeLogger(), csv_writer, run_group_fn=fake_run_group)
    stop_event = threading.Event()

    asyncio.run(service.run(None, groups, "content", [], stop_event))

    assert ("B", "SUCCESS", "ok") in csv_calls
    assert any(name == "A" and status == "FAILED" for name, status, _ in csv_calls)


def test_run_calls_on_progress_after_each_terminal_group():
    groups = [Group("A", "urlA"), Group("B", "urlB")]
    results = [(ResultStatus.SUCCESS, "ok"), (ResultStatus.SUCCESS, "ok")]
    csv_calls = []
    service = make_service(results, csv_calls)
    progress_calls = []
    stop_event = threading.Event()

    asyncio.run(
        service.run(
            None, groups, "content", [], stop_event,
            on_progress=lambda d, t: progress_calls.append((d, t)),
        )
    )

    assert progress_calls == [(1, 2), (2, 2)]
