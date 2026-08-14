import asyncio
import threading

from src.config import Group
from src.poster import PosterConfig, PosterService, ResultStatus


class FakeLogger:
    def info(self, msg):
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
