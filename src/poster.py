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
