from __future__ import annotations

from pathlib import Path

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright


class BrowserManager:
    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None

    async def launch(self) -> BrowserContext:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(self.profile_dir),
            headless=False,
        )
        return self._context

    async def get_page(self) -> Page:
        if self._context is None:
            raise RuntimeError("Browser not launched. Call launch() first.")
        if self._context.pages:
            return self._context.pages[0]
        return await self._context.new_page()

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
