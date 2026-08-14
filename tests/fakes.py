from __future__ import annotations

from playwright.async_api import TimeoutError as PWTimeoutError


class FakeLocator:
    def __init__(self, *, should_timeout: bool = False, visible: bool = True):
        self.should_timeout = should_timeout
        self.visible = visible
        self.clicked = False
        self.filled_text: str | None = None
        self.uploaded_files: list[str] | None = None

    @property
    def first(self) -> "FakeLocator":
        return self

    async def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
        if self.should_timeout:
            raise PWTimeoutError("fake timeout")

    async def click(self, timeout: int = 0) -> None:
        if self.should_timeout:
            raise PWTimeoutError("fake timeout")
        self.clicked = True

    async def fill(self, text: str) -> None:
        self.filled_text = text

    async def set_input_files(self, paths: list[str], timeout: int = 0) -> None:
        if self.should_timeout:
            raise PWTimeoutError("fake timeout")
        self.uploaded_files = paths

    async def is_visible(self, timeout: int = 0) -> bool:
        if self.should_timeout:
            raise PWTimeoutError("fake timeout")
        return self.visible


class FakePage:
    def __init__(self):
        self.goto_calls: list[str] = []
        self.reload_calls = 0
        self.should_goto_timeout = False
        self._locators: dict[str, FakeLocator] = {}

    def configure(self, key: str, *, should_timeout: bool = False, visible: bool = True) -> None:
        self._locators[key] = FakeLocator(should_timeout=should_timeout, visible=visible)

    def _get(self, key: str) -> FakeLocator:
        if key not in self._locators:
            self._locators[key] = FakeLocator()
        return self._locators[key]

    async def goto(self, url: str, timeout: int = 0, wait_until: str | None = None) -> None:
        self.goto_calls.append(url)
        if self.should_goto_timeout:
            raise PWTimeoutError("fake timeout")

    def get_by_role(self, role: str, name: str | None = None, exact: bool = False) -> FakeLocator:
        return self._get(f"role:{role}:{name}")

    def get_by_text(self, text: str) -> FakeLocator:
        return self._get(f"text:{text}")

    def locator(self, selector: str) -> FakeLocator:
        return self._get(f"css:{selector}")

    async def reload(self, wait_until: str | None = None, timeout: int = 0) -> None:
        self.reload_calls += 1
