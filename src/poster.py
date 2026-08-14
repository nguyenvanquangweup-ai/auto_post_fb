from __future__ import annotations

import asyncio
import contextlib
import enum
import logging
import random
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable

from playwright.async_api import Page, TimeoutError as PWTimeoutError

from src.config import Group
from src.logger import SUCCESS_LEVEL
from src.selectors import SEL


class _SafeSubstDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def format_content(content: str, group_name: str) -> str:
    return content.format_map(_SafeSubstDict(group_name=group_name))


@dataclass
class GroupTask:
    group: Group
    attempts: int = 0


class GroupQueue:
    def __init__(self, groups: list[Group]):
        self._queue: deque[GroupTask] = deque(GroupTask(g) for g in groups)
        self.total = len(groups)
        self.done = 0

    def __len__(self) -> int:
        return len(self._queue)

    def pop_next(self) -> GroupTask | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def requeue(self, task: GroupTask) -> bool:
        task.attempts += 1
        if task.attempts < 2:
            self._queue.append(task)
            return True
        return False

    def mark_done(self) -> None:
        self.done += 1


class PosterError(Exception):
    pass


class GroupNotFoundError(PosterError):
    pass


class ComposerNotFoundError(PosterError):
    pass


class UploadTimeoutError(PosterError):
    pass


class PublishError(PosterError):
    pass


class StoppedByUser(Exception):
    pass


async def _run_cancelable(coro, stop_event: threading.Event, poll: float = 0.2):
    task = asyncio.ensure_future(coro)
    watcher = asyncio.ensure_future(_watch_stop(stop_event, poll))
    done, _ = await asyncio.wait({task, watcher}, return_when=asyncio.FIRST_COMPLETED)
    if task in done:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher
        return task.result()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    raise StoppedByUser()


async def _watch_stop(stop_event: threading.Event, poll: float) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(poll)


class ResultStatus(enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


async def open_group(page: Page, url: str, timeout_ms: int = 15000) -> None:
    try:
        await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
    except PWTimeoutError as exc:
        raise GroupNotFoundError(f"Timeout opening group url: {url}") from exc


async def create_post(page: Page, content: str, timeout_ms: int = 10000) -> None:
    trigger = page.get_by_role("button", name=SEL["create_post_trigger_name"], exact=True)
    try:
        await trigger.click(timeout=timeout_ms)
    except PWTimeoutError as exc:
        raise ComposerNotFoundError("Could not find 'Create post' trigger") from exc

    textbox = page.get_by_role("textbox").first
    try:
        await textbox.wait_for(state="visible", timeout=timeout_ms)
    except PWTimeoutError as exc:
        raise ComposerNotFoundError("Composer textbox did not appear") from exc
    await textbox.fill(content)


async def toggle_anonymous(page: Page, timeout_ms: int = 5000) -> bool:
    switch = page.get_by_role("switch", name=SEL["anonymous_toggle_name"])
    try:
        await switch.wait_for(state="visible", timeout=timeout_ms)
    except PWTimeoutError:
        return False

    if await switch.get_attribute("aria-checked") == "true":
        return True

    try:
        await switch.click(timeout=timeout_ms)
    except PWTimeoutError:
        return False

    ok_btn = page.get_by_role("button", name=SEL["anonymous_confirm_ok_name"], exact=True)
    try:
        await ok_btn.click(timeout=timeout_ms)
    except PWTimeoutError:
        pass
    return True


async def check_anonymous_support(page: Page, url: str, timeout_ms: int = 10000) -> bool:
    await open_group(page, url, timeout_ms)
    trigger = page.get_by_role("button", name=SEL["create_post_trigger_name"], exact=True)
    try:
        await trigger.click(timeout=timeout_ms)
    except PWTimeoutError as exc:
        raise ComposerNotFoundError("Could not find 'Create post' trigger") from exc

    switch = page.get_by_role("switch", name=SEL["anonymous_toggle_name"])
    try:
        await switch.wait_for(state="visible", timeout=timeout_ms)
        supported = True
    except PWTimeoutError:
        supported = False

    await page.keyboard.press("Escape")
    return supported


async def upload_images(page: Page, image_paths: list[str], timeout_ms: int = 20000) -> None:
    if not image_paths:
        return
    file_input = page.locator(SEL["file_input_css"]).first
    try:
        await file_input.set_input_files(image_paths, timeout=timeout_ms)
    except PWTimeoutError as exc:
        raise UploadTimeoutError(f"Failed to attach {len(image_paths)} image(s)") from exc

    try:
        await page.get_by_role("img").first.wait_for(state="visible", timeout=timeout_ms)
    except PWTimeoutError as exc:
        raise UploadTimeoutError("Image preview did not render in time") from exc


async def publish(page: Page, timeout_ms: int = 15000) -> None:
    publish_btn = page.get_by_role("button", name=SEL["publish_button_name"], exact=True)
    try:
        await publish_btn.click(timeout=timeout_ms)
    except PWTimeoutError as exc:
        raise PublishError("Could not click Publish button") from exc


async def detect_result(
    page: Page,
    content_snippet: str,
    verify_feed: bool = False,
    timeout_ms: int = 10000,
) -> ResultStatus:
    try:
        await page.get_by_role("dialog").first.wait_for(state="hidden", timeout=timeout_ms)
    except PWTimeoutError:
        return ResultStatus.FAILED

    # Check if publish button is gone (signal 2: successful publish removes the button)
    try:
        is_visible = await page.get_by_role("button", name=SEL["publish_button_name"], exact=True).is_visible(timeout=timeout_ms)
        if is_visible:
            return ResultStatus.FAILED
    except PWTimeoutError:
        # Timeout on is_visible means button is not visible (gone), which is good
        pass

    if not verify_feed:
        return ResultStatus.UNKNOWN

    try:
        await page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
        found = await page.get_by_text(content_snippet[:20]).first.is_visible(timeout=timeout_ms)
        return ResultStatus.SUCCESS if found else ResultStatus.UNKNOWN
    except PWTimeoutError:
        return ResultStatus.UNKNOWN


@dataclass
class PosterConfig:
    min_delay: float
    max_delay: float
    verify_feed: bool = False


class PosterService:
    def __init__(
        self,
        config: PosterConfig,
        logger: logging.Logger,
        csv_writer: Callable[[str, str, str], None],
        run_group_fn=None,
    ):
        self.config = config
        self.logger = logger
        self.csv_writer = csv_writer
        self._run_group_fn = run_group_fn or self.run_group

    async def run_group(
        self, page: Page, group: Group, content_template: str, images: list[str]
    ) -> tuple[ResultStatus, str]:
        content = format_content(content_template, group.name)
        try:
            await open_group(page, group.url)
            await create_post(page, content)
            if group.anonymous and not await toggle_anonymous(page):
                self.logger.warning(f"{group.name}: group không hỗ trợ đăng ẩn danh, đăng công khai")
            await upload_images(page, images)
            await publish(page)
        except PosterError as exc:
            return ResultStatus.FAILED, str(exc)
        status = await detect_result(page, content, verify_feed=self.config.verify_feed)
        return status, status.value

    async def run(
        self,
        page: Page,
        groups: list[Group],
        content_template: str,
        images: list[str],
        stop_event: threading.Event,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        gq = GroupQueue(groups)
        while len(gq) > 0:
            if stop_event.is_set():
                self.logger.info("Stopped by user")
                break
            task = gq.pop_next()
            try:
                status, message = await _run_cancelable(
                    self._run_group_fn(page, task.group, content_template, images), stop_event
                )
            except StoppedByUser:
                self.logger.info("Stopped by user")
                break
            except Exception as exc:
                self.logger.exception(f"{task.group.name}: unexpected error")
                status, message = ResultStatus.FAILED, str(exc)
            if status == ResultStatus.FAILED and gq.requeue(task):
                self.logger.info(f"{task.group.name}: retry scheduled (attempt {task.attempts})")
            else:
                gq.mark_done()
                self.csv_writer(task.group.name, status.value, message)
                result_line = f"{task.group.name}: {status.value} ({gq.done}/{gq.total})"
                if status == ResultStatus.SUCCESS:
                    self.logger.log(SUCCESS_LEVEL, result_line)
                elif status == ResultStatus.FAILED:
                    self.logger.error(result_line)
                else:
                    self.logger.warning(result_line)
                if on_progress:
                    on_progress(gq.done, gq.total)
            if len(gq) > 0:
                delay = random.uniform(self.config.min_delay, self.config.max_delay)
                await self._interruptible_sleep(delay, stop_event)

    @staticmethod
    async def _interruptible_sleep(seconds: float, stop_event: threading.Event, step: float = 0.5) -> None:
        elapsed = 0.0
        while elapsed < seconds and not stop_event.is_set():
            await asyncio.sleep(min(step, seconds - elapsed))
            elapsed += step
