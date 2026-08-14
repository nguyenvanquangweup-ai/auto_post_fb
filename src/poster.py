from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from src.config import Group


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


import enum

from playwright.async_api import TimeoutError as PWTimeoutError

from src.selectors import SEL


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


class ResultStatus(enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


async def open_group(page, url: str, timeout_ms: int = 15000) -> None:
    try:
        await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
    except PWTimeoutError as exc:
        raise GroupNotFoundError(f"Timeout opening group url: {url}") from exc


async def create_post(page, content: str, timeout_ms: int = 10000) -> None:
    trigger = page.get_by_role("button", name=SEL["create_post_trigger_name"])
    try:
        await trigger.click(timeout=timeout_ms)
    except PWTimeoutError as exc:
        raise ComposerNotFoundError("Could not find 'Create post' trigger") from exc

    textbox = page.get_by_role("textbox")
    try:
        await textbox.wait_for(state="visible", timeout=timeout_ms)
    except PWTimeoutError as exc:
        raise ComposerNotFoundError("Composer textbox did not appear") from exc
    await textbox.fill(content)


async def upload_images(page, image_paths: list[str], timeout_ms: int = 20000) -> None:
    if not image_paths:
        return
    file_input = page.locator(SEL["file_input_css"])
    try:
        await file_input.set_input_files(image_paths, timeout=timeout_ms)
    except PWTimeoutError as exc:
        raise UploadTimeoutError(f"Failed to attach {len(image_paths)} image(s)") from exc

    try:
        await page.get_by_role("img").first.wait_for(state="visible", timeout=timeout_ms)
    except PWTimeoutError as exc:
        raise UploadTimeoutError("Image preview did not render in time") from exc


async def publish(page, timeout_ms: int = 15000) -> None:
    publish_btn = page.get_by_role("button", name=SEL["publish_button_name"])
    try:
        await publish_btn.click(timeout=timeout_ms)
    except PWTimeoutError as exc:
        raise PublishError("Could not click Publish button") from exc


async def detect_result(
    page,
    content_snippet: str,
    verify_feed: bool = False,
    timeout_ms: int = 10000,
) -> ResultStatus:
    try:
        await page.get_by_role("dialog").wait_for(state="hidden", timeout=timeout_ms)
    except PWTimeoutError:
        return ResultStatus.FAILED

    if not verify_feed:
        return ResultStatus.UNKNOWN

    try:
        await page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
        found = await page.get_by_text(content_snippet[:20]).first.is_visible(timeout=timeout_ms)
        return ResultStatus.SUCCESS if found else ResultStatus.UNKNOWN
    except PWTimeoutError:
        return ResultStatus.UNKNOWN
