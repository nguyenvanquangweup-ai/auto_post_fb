# Facebook Rental Auto Poster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python desktop tool that posts 1 text+images post to multiple Facebook Groups via Playwright + persistent Chrome profile, controlled from a CustomTkinter UI.

**Architecture:** UI thread (CustomTkinter mainloop) never touches Playwright directly. A background thread runs `asyncio.run()` over a `PosterService` that drives one reused `Page` through each selected group (open → create post → upload images → publish → detect result), with a retry-to-end-of-queue policy and multi-signal result detection. UI and worker talk only through `queue.Queue`.

**Tech Stack:** Python 3.12, Playwright (async, Chromium persistent context, non-headless), CustomTkinter, Pillow, pandas (CSV), pytest + pytest-asyncio for the testable pure/logic layers.

**Spec:** `docs/superpowers/specs/2026-08-14-facebook-rental-auto-poster-design.md`

## Global Constraints

- Python 3.12, full type hints on all function signatures.
- No Facebook Graph API. Browser automation only, via `chromium.launch_persistent_context`, `headless=False`.
- Selectors use `page.get_by_role()` / `get_by_label()` / `get_by_text()` (aria-label based), centralized in `src/selectors.py`, never inlined in flow logic.
- Retry policy: a `GroupTask` starts at `attempts = 0`. On failure, `attempts += 1`; if `attempts < 2` requeue at the **end** of the queue; if `attempts >= 2` the group is terminally FAILED. (2 total attempts per group, matches the approved spec §5 exactly — do not "fix" this to 3 attempts.)
- `detect_result()` returns `SUCCESS | FAILED | UNKNOWN` (an enum `ResultStatus`), never a bare bool. `UNKNOWN` is terminal (recorded, not retried).
- No PyInstaller/.exe packaging — run via `python main.py` in a venv.
- Project root is **this repository's root** (`/home/quangnv/dev/auto_up_post_fb`). Do NOT create a nested `facebook_auto_poster/` subfolder — the spec's directory tree describes this repo root itself.
- Everything under `src/` is a plain package (needs `src/__init__.py`); a `tests/` directory is added for the pure-logic test suite even though the spec's literal file list doesn't mention it — this is necessary scaffolding, not scope creep.

---

## File Structure

```
main.py
requirements.txt
pytest.ini
.gitignore
config/groups.json
config/post.json
assets/images/.gitkeep
browser/.gitkeep
logs/.gitkeep
src/__init__.py
src/config.py       # Group, PostConfig dataclasses; load/save/validate
src/logger.py       # QueueLogHandler, setup_logging, write_csv_result
src/selectors.py    # SEL dict — all Facebook aria-label/role selectors
src/poster.py       # ResultStatus, format_content, GroupQueue, exceptions,
                     # action functions, PosterConfig, PosterService
src/browser.py      # BrowserManager (persistent context lifecycle)
src/ui.py           # App(ctk.CTk) — full desktop UI
tests/__init__.py
tests/fakes.py       # FakePage / FakeLocator test doubles
tests/test_config.py
tests/test_logger.py
tests/test_poster_pure.py     # format_content + GroupQueue
tests/test_poster_actions.py  # open_group..detect_result via FakePage
tests/test_poster_service.py  # PosterService.run orchestration
README.md
```

Rationale: `src/poster.py` stays one file (matches the spec's literal file list) but grows across three tasks — pure logic, action functions, orchestration — each independently testable. `src/selectors.py` is split out per the spec's own escape clause ("hoặc `src/selectors.py` nếu file dài"). `src/browser.py` and `src/ui.py` are not unit-tested (they need a real browser / real display); they get an explicit manual verification step instead, per project convention that UI/live-integration code is verified by running it, not faked.

---

### Task 1: Project scaffolding & sample configs

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `config/groups.json`
- Create: `config/post.json`
- Create: `assets/images/.gitkeep`
- Create: `browser/.gitkeep`
- Create: `logs/.gitkeep`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Produces: a working `pip install -r requirements.txt` environment and importable `src`/`tests` packages for every later task.

- [ ] **Step 1: Create `requirements.txt`**

```
playwright>=1.47
customtkinter>=5.2
pillow>=10.4
pandas>=2.2
pytest>=8.3
pytest-asyncio>=0.24
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 3: Create `.gitignore`**

```
venv/
__pycache__/
*.pyc
browser/chrome_profile/
logs/*.log
logs/*.csv
.pytest_cache/
```

- [ ] **Step 4: Create `config/groups.json`**

```json
[
  {
    "name": "Cho thuê trọ Hà Nội",
    "url": "https://facebook.com/groups/xxxxx"
  },
  {
    "name": "Trọ Thanh Xuân",
    "url": "https://facebook.com/groups/yyyyy"
  }
]
```

- [ ] **Step 5: Create `config/post.json`**

```json
{
  "content": "Cho thuê phòng trọ khu vực {group_name}, đầy đủ tiện nghi, giá tốt. Liên hệ ngay để xem phòng!",
  "images": []
}
```

- [ ] **Step 6: Create empty placeholder files**

```bash
touch assets/images/.gitkeep browser/.gitkeep logs/.gitkeep src/__init__.py tests/__init__.py
```

- [ ] **Step 7: Install dependencies and Playwright browsers**

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Expected: no errors. `pip show playwright customtkinter pillow pandas pytest pytest-asyncio` all resolve.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt pytest.ini .gitignore config/ assets/images/.gitkeep browser/.gitkeep logs/.gitkeep src/__init__.py tests/__init__.py
git commit -m "chore: scaffold project structure and sample configs"
```

---

### Task 2: `src/config.py` — Group/PostConfig load, save, validate

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `class Group: name: str, url: str` (dataclass, eq by value)
  - `class PostConfig: content: str, images: list[str]` (dataclass, eq by value)
  - `class ConfigError(Exception)`
  - `load_groups(path: Path) -> list[Group]`
  - `save_groups(path: Path, groups: list[Group]) -> None`
  - `load_post_config(path: Path) -> PostConfig`
  - `save_post_config(path: Path, post: PostConfig) -> None`
  - `validate_post_config(post: PostConfig, base_dir: Path) -> list[str]` (returns missing image paths; empty list = all present)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
import json

import pytest

from src.config import (
    ConfigError,
    Group,
    PostConfig,
    load_groups,
    load_post_config,
    save_groups,
    save_post_config,
    validate_post_config,
)


def test_load_groups_parses_json(tmp_path):
    p = tmp_path / "groups.json"
    p.write_text(json.dumps([{"name": "A", "url": "https://facebook.com/groups/1"}]), encoding="utf-8")
    groups = load_groups(p)
    assert groups == [Group(name="A", url="https://facebook.com/groups/1")]


def test_save_groups_writes_json(tmp_path):
    p = tmp_path / "groups.json"
    save_groups(p, [Group(name="A", url="https://facebook.com/groups/1")])
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == [{"name": "A", "url": "https://facebook.com/groups/1"}]


def test_load_groups_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_groups(tmp_path / "missing.json")


def test_load_post_config_parses_json(tmp_path):
    p = tmp_path / "post.json"
    p.write_text(json.dumps({"content": "Hello {group_name}", "images": ["assets/images/a.jpg"]}), encoding="utf-8")
    post = load_post_config(p)
    assert post == PostConfig(content="Hello {group_name}", images=["assets/images/a.jpg"])


def test_save_post_config_writes_json(tmp_path):
    p = tmp_path / "post.json"
    save_post_config(p, PostConfig(content="Hi", images=[]))
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"content": "Hi", "images": []}


def test_validate_post_config_reports_missing_images(tmp_path):
    (tmp_path / "assets" / "images").mkdir(parents=True)
    (tmp_path / "assets" / "images" / "a.jpg").write_bytes(b"fake")
    post = PostConfig(content="Hi", images=["assets/images/a.jpg", "assets/images/missing.jpg"])
    missing = validate_post_config(post, tmp_path)
    assert missing == ["assets/images/missing.jpg"]


def test_validate_post_config_all_present_returns_empty(tmp_path):
    (tmp_path / "assets" / "images").mkdir(parents=True)
    (tmp_path / "assets" / "images" / "a.jpg").write_bytes(b"fake")
    post = PostConfig(content="Hi", images=["assets/images/a.jpg"])
    assert validate_post_config(post, tmp_path) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: Implement `src/config.py`**

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass
class Group:
    name: str
    url: str


@dataclass
class PostConfig:
    content: str
    images: list[str] = field(default_factory=list)


def load_groups(path: Path) -> list[Group]:
    if not path.exists():
        raise ConfigError(f"Groups file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Group(name=item["name"], url=item["url"]) for item in data]


def save_groups(path: Path, groups: list[Group]) -> None:
    data = [asdict(g) for g in groups]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_post_config(path: Path) -> PostConfig:
    if not path.exists():
        raise ConfigError(f"Post config file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return PostConfig(content=data["content"], images=data.get("images", []))


def save_post_config(path: Path, post: PostConfig) -> None:
    path.write_text(json.dumps(asdict(post), ensure_ascii=False, indent=2), encoding="utf-8")


def validate_post_config(post: PostConfig, base_dir: Path) -> list[str]:
    missing = []
    for rel_path in post.images:
        if not (base_dir / rel_path).exists():
            missing.append(rel_path)
    return missing
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add config load/save/validate for groups and post"
```

---

### Task 3: `src/logger.py` — QueueLogHandler, setup_logging, CSV writer

**Files:**
- Create: `src/logger.py`
- Test: `tests/test_logger.py`

**Interfaces:**
- Consumes: none (stdlib `logging`, `csv` only)
- Produces:
  - `class QueueLogHandler(logging.Handler): __init__(self, log_queue: queue.Queue)` — puts `(record.levelname: str, formatted_message: str)` tuples
  - `setup_logging(log_queue: queue.Queue, log_dir: Path) -> logging.Logger` — logger named `"facebook_auto_poster"`, writes `log_dir/app.log`, console, and the queue
  - `write_csv_result(csv_path: Path, timestamp: str, group_name: str, status: str, message: str) -> None` — appends a row, writing the header row `["time", "group", "status", "message"]` on first write

- [ ] **Step 1: Write the failing tests**

Create `tests/test_logger.py`:

```python
import csv
import logging
import queue

from src.logger import QueueLogHandler, setup_logging, write_csv_result


def test_queue_log_handler_puts_level_and_message():
    q = queue.Queue()
    handler = QueueLogHandler(q)
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="Posted successfully.", args=(), exc_info=None,
    )
    handler.emit(record)
    level, message = q.get_nowait()
    assert level == "INFO"
    assert message == "Posted successfully."


def test_setup_logging_creates_log_file(tmp_path):
    q = queue.Queue()
    logger = setup_logging(q, tmp_path)
    logger.info("hello")
    for h in logger.handlers:
        h.flush()
    log_file = tmp_path / "app.log"
    assert log_file.exists()
    assert "hello" in log_file.read_text(encoding="utf-8")


def test_write_csv_result_appends_row_with_header(tmp_path):
    csv_path = tmp_path / "2026-08-14.csv"
    write_csv_result(csv_path, "2026-08-14 17:20:00", "Group A", "SUCCESS", "Posted successfully.")
    write_csv_result(csv_path, "2026-08-14 17:25:00", "Group B", "FAILED", "Timeout")
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["time", "group", "status", "message"]
    assert rows[1] == ["2026-08-14 17:20:00", "Group A", "SUCCESS", "Posted successfully."]
    assert rows[2] == ["2026-08-14 17:25:00", "Group B", "FAILED", "Timeout"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_logger.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.logger'`

- [ ] **Step 3: Implement `src/logger.py`**

```python
from __future__ import annotations

import csv
import logging
import queue
from pathlib import Path


class QueueLogHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        self.log_queue.put((record.levelname, self.format(record)))


def setup_logging(log_queue: queue.Queue, log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("facebook_auto_poster")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(file_formatter)
    logger.addHandler(console_handler)

    queue_handler = QueueLogHandler(log_queue)
    queue_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(queue_handler)

    return logger


def write_csv_result(csv_path: Path, timestamp: str, group_name: str, status: str, message: str) -> None:
    is_new = not csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["time", "group", "status", "message"])
        writer.writerow([timestamp, group_name, status, message])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_logger.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/logger.py tests/test_logger.py
git commit -m "feat: add logging setup with queue handler and CSV result writer"
```

---

### Task 4: `src/poster.py` part A — `format_content` and `GroupQueue` retry logic

**Files:**
- Create: `src/poster.py`
- Test: `tests/test_poster_pure.py`
- Modify: none

**Interfaces:**
- Consumes: `src.config.Group`
- Produces:
  - `format_content(content: str, group_name: str) -> str` — substitutes `{group_name}`, leaves any other `{...}` untouched, no `KeyError`
  - `@dataclass class GroupTask: group: Group, attempts: int = 0`
  - `class GroupQueue: __init__(self, groups: list[Group])`, `.total: int`, `.done: int`, `__len__`, `.pop_next() -> GroupTask | None`, `.requeue(task: GroupTask) -> bool`, `.mark_done() -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_poster_pure.py`:

```python
from src.config import Group
from src.poster import GroupQueue, format_content


def test_format_content_no_placeholder_unchanged():
    assert format_content("Hello world", "Group A") == "Hello world"


def test_format_content_substitutes_group_name():
    assert format_content("Cho thue tro {group_name}", "Cau Giay") == "Cho thue tro Cau Giay"


def test_format_content_leaves_unknown_braces_untouched():
    result = format_content("Giam gia {mystery} nhe {group_name}", "Ha Noi")
    assert result == "Giam gia {mystery} nhe Ha Noi"


def test_group_queue_pop_next_fifo():
    groups = [Group("A", "urlA"), Group("B", "urlB")]
    gq = GroupQueue(groups)
    assert gq.total == 2
    assert gq.pop_next().group.name == "A"
    assert gq.pop_next().group.name == "B"
    assert gq.pop_next() is None


def test_group_queue_requeue_then_gives_up():
    gq = GroupQueue([Group("A", "urlA")])
    task = gq.pop_next()
    assert gq.requeue(task) is True
    assert task.attempts == 1

    task2 = gq.pop_next()
    assert task2 is task
    assert gq.requeue(task2) is False
    assert task2.attempts == 2


def test_group_queue_mark_done_tracks_progress():
    gq = GroupQueue([Group("A", "urlA"), Group("B", "urlB")])
    assert gq.done == 0
    gq.mark_done()
    gq.mark_done()
    assert gq.done == 2
    assert gq.total == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_poster_pure.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.poster'`

- [ ] **Step 3: Implement `src/poster.py` (initial content)**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_poster_pure.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/poster.py tests/test_poster_pure.py
git commit -m "feat: add content placeholder formatting and retry-to-end group queue"
```

---

### Task 5: `src/selectors.py` + `src/poster.py` part B — action functions

**Files:**
- Create: `src/selectors.py`
- Modify: `src/poster.py` (append below `GroupQueue`)
- Create: `tests/fakes.py`
- Test: `tests/test_poster_actions.py`

**Interfaces:**
- Consumes: `GroupQueue`/`format_content` from Task 4 (same file, no import needed)
- Produces:
  - `SEL: dict[str, str]` in `src/selectors.py`
  - Exceptions: `class PosterError(Exception)`, `GroupNotFoundError`, `ComposerNotFoundError`, `UploadTimeoutError`, `PublishError` (all in `src/poster.py`)
  - `class ResultStatus(enum.Enum): SUCCESS = "SUCCESS"; FAILED = "FAILED"; UNKNOWN = "UNKNOWN"`
  - `async open_group(page, url: str, timeout_ms: int = 15000) -> None`
  - `async create_post(page, content: str, timeout_ms: int = 10000) -> None`
  - `async upload_images(page, image_paths: list[str], timeout_ms: int = 20000) -> None`
  - `async publish(page, timeout_ms: int = 15000) -> None`
  - `async detect_result(page, content_snippet: str, verify_feed: bool = False, timeout_ms: int = 10000) -> ResultStatus`
  - Test double in `tests/fakes.py`: `class FakePage`, `class FakeLocator`, both used by every later poster test

**Note on selector values:** Facebook's DOM/aria-labels drift over time. The values below are current best-known labels for the post-composer flow; when running against live Facebook for the first time, open the group, use Playwright's inspector (`PWDEBUG=1`) or browser devtools to confirm/adjust `SEL` — this is a live-integration detail called out in spec §3, not a plan placeholder.

- [ ] **Step 1: Create `src/selectors.py`**

```python
SEL = {
    "create_post_trigger_name": "Create post",
    "publish_button_name": "Post",
    "file_input_css": "input[type='file']",
}
```

- [ ] **Step 2: Create `tests/fakes.py`**

```python
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

    def get_by_role(self, role: str, name: str | None = None) -> FakeLocator:
        return self._get(f"role:{role}:{name}")

    def get_by_text(self, text: str) -> FakeLocator:
        return self._get(f"text:{text}")

    def locator(self, selector: str) -> FakeLocator:
        return self._get(f"css:{selector}")

    async def reload(self, wait_until: str | None = None, timeout: int = 0) -> None:
        self.reload_calls += 1
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_poster_actions.py`:

```python
import pytest

from src.poster import (
    ComposerNotFoundError,
    GroupNotFoundError,
    PublishError,
    ResultStatus,
    UploadTimeoutError,
    create_post,
    detect_result,
    open_group,
    publish,
    upload_images,
)
from tests.fakes import FakePage


async def test_open_group_navigates_to_url():
    page = FakePage()
    await open_group(page, "https://facebook.com/groups/1")
    assert page.goto_calls == ["https://facebook.com/groups/1"]


async def test_open_group_timeout_raises_group_not_found():
    page = FakePage()
    page.should_goto_timeout = True
    with pytest.raises(GroupNotFoundError):
        await open_group(page, "https://facebook.com/groups/1")


async def test_create_post_clicks_trigger_and_fills_content():
    page = FakePage()
    await create_post(page, "Hello world")
    trigger = page._get("role:button:Create post")
    textbox = page._get("role:textbox:None")
    assert trigger.clicked is True
    assert textbox.filled_text == "Hello world"


async def test_create_post_missing_trigger_raises_composer_not_found():
    page = FakePage()
    page.configure("role:button:Create post", should_timeout=True)
    with pytest.raises(ComposerNotFoundError):
        await create_post(page, "Hello world")


async def test_create_post_missing_textbox_raises_composer_not_found():
    page = FakePage()
    page.configure("role:textbox:None", should_timeout=True)
    with pytest.raises(ComposerNotFoundError):
        await create_post(page, "Hello world")


async def test_upload_images_empty_list_is_noop():
    page = FakePage()
    await upload_images(page, [])
    assert "css:input[type='file']" not in page._locators


async def test_upload_images_success_sets_files():
    page = FakePage()
    await upload_images(page, ["a.jpg", "b.jpg"])
    file_input = page._get("css:input[type='file']")
    assert file_input.uploaded_files == ["a.jpg", "b.jpg"]


async def test_upload_images_timeout_raises_upload_timeout_error():
    page = FakePage()
    page.configure("css:input[type='file']", should_timeout=True)
    with pytest.raises(UploadTimeoutError):
        await upload_images(page, ["a.jpg"])


async def test_publish_clicks_publish_button():
    page = FakePage()
    await publish(page)
    btn = page._get("role:button:Post")
    assert btn.clicked is True


async def test_publish_timeout_raises_publish_error():
    page = FakePage()
    page.configure("role:button:Post", should_timeout=True)
    with pytest.raises(PublishError):
        await publish(page)


async def test_detect_result_dialog_open_returns_failed():
    page = FakePage()
    page.configure("role:dialog:None", should_timeout=True)
    status = await detect_result(page, "Hello world")
    assert status == ResultStatus.FAILED


async def test_detect_result_dialog_closed_no_verify_returns_unknown():
    page = FakePage()
    status = await detect_result(page, "Hello world", verify_feed=False)
    assert status == ResultStatus.UNKNOWN


async def test_detect_result_verify_feed_found_returns_success():
    page = FakePage()
    page.configure("text:Hello world", visible=True)
    status = await detect_result(page, "Hello world", verify_feed=True)
    assert status == ResultStatus.SUCCESS


async def test_detect_result_verify_feed_not_found_returns_unknown():
    page = FakePage()
    page.configure("text:Hello world", visible=False)
    status = await detect_result(page, "Hello world", verify_feed=True)
    assert status == ResultStatus.UNKNOWN
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_poster_actions.py -v`
Expected: FAIL — `ImportError` (names not defined in `src.poster`)

- [ ] **Step 5: Append to `src/poster.py`**

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_poster_actions.py -v`
Expected: 14 passed

- [ ] **Step 7: Commit**

```bash
git add src/selectors.py src/poster.py tests/fakes.py tests/test_poster_actions.py
git commit -m "feat: add Facebook post action functions with multi-signal detect_result"
```

---

### Task 6: `src/poster.py` part C — `PosterConfig` and `PosterService` orchestration

**Files:**
- Modify: `src/poster.py` (append below `detect_result`)
- Test: `tests/test_poster_service.py`

**Interfaces:**
- Consumes: `GroupQueue`, `format_content`, `ResultStatus`, `PosterError`, `open_group`, `create_post`, `upload_images`, `publish`, `detect_result` (all same file, Tasks 4–5), `src.config.Group`
- Produces:
  - `@dataclass class PosterConfig: min_delay: float, max_delay: float, verify_feed: bool = False`
  - `class PosterService.__init__(self, config: PosterConfig, logger: logging.Logger, csv_writer: Callable[[str, str, str], None], run_group_fn=None)`
  - `async PosterService.run_group(self, page, group: Group, content_template: str, images: list[str]) -> tuple[ResultStatus, str]`
  - `async PosterService.run(self, page, groups: list[Group], content_template: str, images: list[str], stop_event: threading.Event, on_progress: Callable[[int, int], None] | None = None) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_poster_service.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_poster_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'PosterConfig'`

- [ ] **Step 3: Append to `src/poster.py`**

```python
import asyncio
import logging
import random
import threading
from dataclasses import dataclass
from typing import Callable

from src.config import Group


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
        self, page, group: Group, content_template: str, images: list[str]
    ) -> tuple[ResultStatus, str]:
        content = format_content(content_template, group.name)
        try:
            await open_group(page, group.url)
            await create_post(page, content)
            await upload_images(page, images)
            await publish(page)
        except PosterError as exc:
            return ResultStatus.FAILED, str(exc)
        status = await detect_result(page, content, verify_feed=self.config.verify_feed)
        return status, status.value

    async def run(
        self,
        page,
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
            status, message = await self._run_group_fn(page, task.group, content_template, images)
            if status == ResultStatus.FAILED and gq.requeue(task):
                self.logger.info(f"{task.group.name}: retry scheduled (attempt {task.attempts})")
            else:
                gq.mark_done()
                self.csv_writer(task.group.name, status.value, message)
                self.logger.info(f"{task.group.name}: {status.value} ({gq.done}/{gq.total})")
                if on_progress:
                    on_progress(gq.done, gq.total)
            delay = random.uniform(self.config.min_delay, self.config.max_delay)
            await asyncio.sleep(delay)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_poster_service.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full test suite so far**

Run: `pytest -v`
Expected: all tests from Tasks 2–6 pass (config, logger, poster pure/actions/service)

- [ ] **Step 6: Commit**

```bash
git add src/poster.py tests/test_poster_service.py
git commit -m "feat: add PosterService orchestration with retry queue and progress callback"
```

---

### Task 7: `src/browser.py` — persistent Chrome profile lifecycle

**Files:**
- Create: `src/browser.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces:
  - `class BrowserManager.__init__(self, profile_dir: Path)`
  - `async BrowserManager.launch(self) -> BrowserContext`
  - `async BrowserManager.get_page(self) -> Page` (reuses the first open tab if present, else opens a new one)
  - `async BrowserManager.close(self) -> None`

No automated test — this launches a real Chromium process and can't run in a unit test. Manual verification step at the end covers it.

- [ ] **Step 1: Implement `src/browser.py`**

```python
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
```

- [ ] **Step 2: Manual smoke test**

Run:

```bash
python -c "
import asyncio
from pathlib import Path
from src.browser import BrowserManager

async def main():
    bm = BrowserManager(Path('browser/chrome_profile'))
    await bm.launch()
    page = await bm.get_page()
    await page.goto('https://facebook.com')
    input('Chrome opened and navigated to facebook.com — press Enter to close...')
    await bm.close()

asyncio.run(main())
"
```

Expected: a non-headless Chrome window opens, navigates to facebook.com, and `browser/chrome_profile/` is populated on disk. Closing behaves cleanly (no hung process).

- [ ] **Step 3: Commit**

```bash
git add src/browser.py
git commit -m "feat: add persistent Chrome profile browser manager"
```

---

### Task 8: `src/ui.py` + `main.py` — desktop UI and entry point

**Files:**
- Create: `src/ui.py`
- Create: `main.py`

**Interfaces:**
- Consumes: everything from Tasks 2, 3, 6, 7 — `src.config.{Group, PostConfig, load_groups, save_groups, load_post_config, save_post_config, validate_post_config}`, `src.logger.{setup_logging, write_csv_result}`, `src.poster.{PosterConfig, PosterService}`, `src.browser.BrowserManager`
- Produces: `class App(ctk.CTk).__init__(self, base_dir: Path)`, `main()` entry point

No automated test — CustomTkinter widgets need a real display and the posting flow needs a real logged-in Facebook session. Verified manually in Step 2.

- [ ] **Step 1: Implement `src/ui.py`**

```python
from __future__ import annotations

import asyncio
import queue
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from src.browser import BrowserManager
from src.config import (
    Group,
    PostConfig,
    load_groups,
    load_post_config,
    save_groups,
    save_post_config,
    validate_post_config,
)
from src.logger import setup_logging, write_csv_result
from src.poster import PosterConfig, PosterService

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

LOG_COLORS = {
    "INFO": "#1f6feb",
    "SUCCESS": "#1a7f37",
    "ERROR": "#cf222e",
    "WARNING": "#bf8700",
    "DEBUG": "#57606a",
}


class GroupDialog(ctk.CTkToplevel):
    def __init__(self, master, title: str, name: str = "", url: str = ""):
        super().__init__(master)
        self.title(title)
        self.geometry("420x180")
        self.result: tuple[str, str] | None = None

        ctk.CTkLabel(self, text="Tên group:").pack(anchor="w", padx=16, pady=(16, 0))
        self.name_entry = ctk.CTkEntry(self, width=380)
        self.name_entry.insert(0, name)
        self.name_entry.pack(padx=16, pady=(0, 8))

        ctk.CTkLabel(self, text="URL:").pack(anchor="w", padx=16)
        self.url_entry = ctk.CTkEntry(self, width=380)
        self.url_entry.insert(0, url)
        self.url_entry.pack(padx=16, pady=(0, 8))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=12)
        ctk.CTkButton(btn_frame, text="Lưu", command=self._on_save).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="Huỷ", fg_color="gray", command=self.destroy).pack(side="left", padx=8)

        self.grab_set()

    def _on_save(self):
        name = self.name_entry.get().strip()
        url = self.url_entry.get().strip()
        if not name or not url:
            messagebox.showerror("Lỗi", "Tên và URL không được để trống")
            return
        self.result = (name, url)
        self.destroy()


class App(ctk.CTk):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.base_dir = base_dir
        self.groups_path = base_dir / "config" / "groups.json"
        self.post_path = base_dir / "config" / "post.json"
        self.profile_dir = base_dir / "browser" / "chrome_profile"
        self.logs_dir = base_dir / "logs"

        self.title("Facebook Rental Auto Poster")
        self.geometry("1100x700")

        self.groups: list[Group] = []
        self.group_vars: list[ctk.BooleanVar] = []
        self.image_paths: list[str] = []
        self.selected_image_index: int | None = None
        self.log_queue: queue.Queue = queue.Queue()
        self.progress_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread: threading.Thread | None = None

        self.logger = setup_logging(self.log_queue, self.logs_dir)

        self._build_ui()
        self._load_initial_config()
        self.after(100, self._drain_log_queue)
        self.after(100, self._drain_progress_queue)

    # ---------- UI construction ----------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self)
        left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        right = ctk.CTkFrame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)

        self._build_left_panel(left)
        self._build_right_panel(right)

    def _build_left_panel(self, parent):
        ctk.CTkLabel(parent, text="Nội dung bài đăng", font=("", 14, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        self.content_box = ctk.CTkTextbox(parent, height=180)
        self.content_box.pack(fill="x", padx=12)

        ctk.CTkLabel(parent, text="Ảnh đính kèm", font=("", 14, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        img_btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        img_btn_frame.pack(fill="x", padx=12)
        ctk.CTkButton(img_btn_frame, text="Add Images", command=self._add_images).pack(side="left", padx=(0, 8))
        ctk.CTkButton(img_btn_frame, text="Remove", fg_color="gray", command=self._remove_selected_image).pack(side="left")

        self.image_frame = ctk.CTkScrollableFrame(parent, height=180)
        self.image_frame.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        ctk.CTkLabel(parent, text="Delay (giây)", font=("", 14, "bold")).pack(anchor="w", padx=12)
        delay_frame = ctk.CTkFrame(parent, fg_color="transparent")
        delay_frame.pack(fill="x", padx=12, pady=(4, 12))
        ctk.CTkLabel(delay_frame, text="Min:").pack(side="left")
        self.min_delay_entry = ctk.CTkEntry(delay_frame, width=60)
        self.min_delay_entry.insert(0, "20")
        self.min_delay_entry.pack(side="left", padx=(4, 16))
        ctk.CTkLabel(delay_frame, text="Max:").pack(side="left")
        self.max_delay_entry = ctk.CTkEntry(delay_frame, width=60)
        self.max_delay_entry.insert(0, "40")
        self.max_delay_entry.pack(side="left", padx=4)

    def _build_right_panel(self, parent):
        ctk.CTkLabel(parent, text="Facebook Groups", font=("", 14, "bold")).pack(anchor="w", padx=12, pady=(12, 4))

        self.group_table = ctk.CTkScrollableFrame(parent, height=220)
        self.group_table.pack(fill="both", expand=True, padx=12)

        group_btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        group_btn_frame.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(group_btn_frame, text="Add Group", command=self._add_group).pack(side="left", padx=(0, 6))
        ctk.CTkButton(group_btn_frame, text="Edit", command=self._edit_group).pack(side="left", padx=6)
        ctk.CTkButton(group_btn_frame, text="Delete", fg_color="#cf222e", command=self._delete_group).pack(side="left", padx=6)
        ctk.CTkButton(group_btn_frame, text="Import JSON", command=self._import_groups_json).pack(side="left", padx=6)

        control_frame = ctk.CTkFrame(parent, fg_color="transparent")
        control_frame.pack(fill="x", padx=12, pady=(4, 8))
        ctk.CTkButton(control_frame, text="Login Facebook", command=self._on_login).pack(side="left", padx=(0, 6))
        ctk.CTkButton(control_frame, text="Test 1 Group", command=self._on_test_one).pack(side="left", padx=6)
        ctk.CTkButton(control_frame, text="Start Posting", fg_color="#1a7f37", command=self._on_start).pack(side="left", padx=6)
        ctk.CTkButton(control_frame, text="Stop", fg_color="#cf222e", command=self._on_stop).pack(side="left", padx=6)

        self.progress_label = ctk.CTkLabel(parent, text="0 / 0 Groups")
        self.progress_label.pack(anchor="w", padx=12)
        self.progress_bar = ctk.CTkProgressBar(parent)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(parent, text="Log", font=("", 14, "bold")).pack(anchor="w", padx=12)
        self.log_box = ctk.CTkTextbox(parent, height=200)
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.log_box.configure(state="disabled")

    # ---------- config load/save ----------

    def _load_initial_config(self):
        try:
            self.groups = load_groups(self.groups_path)
        except Exception:
            self.groups = []
        self._refresh_group_table()

        try:
            post = load_post_config(self.post_path)
        except Exception:
            post = PostConfig(content="", images=[])
        self.content_box.insert("1.0", post.content)
        self.image_paths = list(post.images)
        self._refresh_image_list()

    def _save_current_post_config(self) -> PostConfig:
        content = self.content_box.get("1.0", "end").rstrip("\n")
        post = PostConfig(content=content, images=list(self.image_paths))
        save_post_config(self.post_path, post)
        return post

    # ---------- group table ----------

    def _refresh_group_table(self):
        for child in self.group_table.winfo_children():
            child.destroy()
        self.group_vars = []
        for group in self.groups:
            var = ctk.BooleanVar(value=True)
            row = ctk.CTkFrame(self.group_table, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkCheckBox(row, text="", variable=var, width=20).pack(side="left")
            ctk.CTkLabel(row, text=group.name, width=180, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=group.url, anchor="w", text_color="gray").pack(side="left", padx=4)
            self.group_vars.append(var)

    def _selected_groups(self) -> list[Group]:
        return [g for g, v in zip(self.groups, self.group_vars) if v.get()]

    def _add_group(self):
        dialog = GroupDialog(self, "Add Group")
        self.wait_window(dialog)
        if dialog.result:
            name, url = dialog.result
            self.groups.append(Group(name=name, url=url))
            save_groups(self.groups_path, self.groups)
            self._refresh_group_table()

    def _edit_group(self):
        selected = [i for i, v in enumerate(self.group_vars) if v.get()]
        if len(selected) != 1:
            messagebox.showinfo("Edit Group", "Chọn đúng 1 group để sửa")
            return
        idx = selected[0]
        group = self.groups[idx]
        dialog = GroupDialog(self, "Edit Group", name=group.name, url=group.url)
        self.wait_window(dialog)
        if dialog.result:
            name, url = dialog.result
            self.groups[idx] = Group(name=name, url=url)
            save_groups(self.groups_path, self.groups)
            self._refresh_group_table()

    def _delete_group(self):
        selected = {i for i, v in enumerate(self.group_vars) if v.get()}
        if not selected:
            messagebox.showinfo("Delete Group", "Chọn ít nhất 1 group để xoá")
            return
        self.groups = [g for i, g in enumerate(self.groups) if i not in selected]
        save_groups(self.groups_path, self.groups)
        self._refresh_group_table()

    def _import_groups_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            imported = load_groups(Path(path))
        except Exception as exc:
            messagebox.showerror("Import lỗi", str(exc))
            return
        self.groups.extend(imported)
        save_groups(self.groups_path, self.groups)
        self._refresh_group_table()

    # ---------- images ----------

    def _add_images(self):
        paths = filedialog.askopenfilenames(filetypes=[("Images", "*.jpg *.jpeg *.png")])
        self.image_paths.extend(paths)
        self._refresh_image_list()

    def _remove_selected_image(self):
        if self.selected_image_index is None:
            return
        del self.image_paths[self.selected_image_index]
        self.selected_image_index = None
        self._refresh_image_list()

    def _refresh_image_list(self):
        for child in self.image_frame.winfo_children():
            child.destroy()
        for idx, path in enumerate(self.image_paths):
            row = ctk.CTkFrame(self.image_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            try:
                img = Image.open(path)
                img.thumbnail((48, 48))
                ctk_img = ctk.CTkImage(light_image=img, size=img.size)
                thumb = ctk.CTkLabel(row, image=ctk_img, text="")
                thumb.image = ctk_img
            except Exception:
                thumb = ctk.CTkLabel(row, text="[ảnh lỗi]")
            thumb.pack(side="left", padx=4)
            label = ctk.CTkLabel(row, text=Path(path).name, anchor="w")
            label.pack(side="left", padx=4)
            row.bind("<Button-1>", lambda e, i=idx: self._select_image(i))
            label.bind("<Button-1>", lambda e, i=idx: self._select_image(i))

    def _select_image(self, idx: int):
        self.selected_image_index = idx

    # ---------- realtime log + progress ----------

    def _drain_log_queue(self):
        try:
            while True:
                level, message = self.log_queue.get_nowait()
                self._append_log(level, message)
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    def _append_log(self, level: str, message: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        tag = f"tag_{level}"
        line_start = self.log_box.index("end-2l")
        line_end = self.log_box.index("end-1l")
        self.log_box.tag_config(tag, foreground=LOG_COLORS.get(level, "#1f2328"))
        self.log_box.tag_add(tag, line_start, line_end)
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _drain_progress_queue(self):
        try:
            while True:
                done, total = self.progress_queue.get_nowait()
                self.progress_label.configure(text=f"{done} / {total} Groups")
                self.progress_bar.set(done / total if total else 0)
        except queue.Empty:
            pass
        self.after(100, self._drain_progress_queue)

    # ---------- worker orchestration ----------

    def _read_delays(self) -> tuple[float, float]:
        try:
            min_d = float(self.min_delay_entry.get())
            max_d = float(self.max_delay_entry.get())
        except ValueError:
            min_d, max_d = 20.0, 40.0
        if max_d < min_d:
            max_d = min_d
        return min_d, max_d

    def _on_login(self):
        self._run_in_worker(self._login_flow)

    def _on_test_one(self):
        selected = self._selected_groups()
        if not selected:
            messagebox.showinfo("Test 1 Group", "Chọn 1 group để test")
            return
        self._run_in_worker(lambda: self._post_flow([selected[0]]))

    def _on_start(self):
        selected = self._selected_groups()
        if not selected:
            messagebox.showinfo("Start Posting", "Chọn ít nhất 1 group")
            return
        self._run_in_worker(lambda: self._post_flow(selected))

    def _on_stop(self):
        self.stop_event.set()

    def _run_in_worker(self, coro_factory):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Đang chạy", "Đang có tác vụ chạy, chờ hoàn thành hoặc bấm Stop")
            return
        self.stop_event = threading.Event()

        def target():
            asyncio.run(coro_factory())

        self.worker_thread = threading.Thread(target=target, daemon=True)
        self.worker_thread.start()

    async def _login_flow(self):
        browser = BrowserManager(self.profile_dir)
        await browser.launch()
        self.logger.info("Đã mở Chrome. Đăng nhập Facebook nếu cần, cửa sổ này giữ nguyên phiên đăng nhập cho lần sau.")

    async def _post_flow(self, groups: list[Group]):
        post = self._save_current_post_config()
        missing = validate_post_config(post, self.base_dir)
        if missing:
            self.logger.error(f"Thiếu ảnh: {', '.join(missing)}")
            return

        min_delay, max_delay = self._read_delays()
        config = PosterConfig(min_delay=min_delay, max_delay=max_delay, verify_feed=False)
        csv_path = self.logs_dir / f"{time.strftime('%Y-%m-%d')}.csv"

        def csv_writer(group_name: str, status: str, message: str):
            write_csv_result(csv_path, time.strftime("%Y-%m-%d %H:%M:%S"), group_name, status, message)

        service = PosterService(config, self.logger, csv_writer)
        self.progress_queue.put((0, len(groups)))

        browser = BrowserManager(self.profile_dir)
        await browser.launch()
        page = await browser.get_page()
        try:
            await service.run(
                page, groups, post.content, list(post.images), self.stop_event,
                on_progress=lambda d, t: self.progress_queue.put((d, t)),
            )
        finally:
            await browser.close()
```

- [ ] **Step 2: Implement `main.py`**

```python
from pathlib import Path

from src.ui import App


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    app = App(base_dir)
    app.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Manual verification**

Run: `python main.py`

Check, in order:
1. Window opens at ~1100x700, white/blue theme, 2 columns.
2. Left: post content textbox pre-filled from `config/post.json`; edit it, it's editable.
3. "Add Images" opens a file picker, selected images show as thumbnails in the scrollable list; clicking a thumbnail row then "Remove" deletes it from the list.
4. Right: group table shows the 2 sample groups from `config/groups.json`, each with a checkbox, name, url.
5. "Add Group" opens a dialog, fill name+url, saves into `config/groups.json` on disk (verify by reading the file) and the table refreshes.
6. "Edit" with exactly one group checked opens the dialog pre-filled; "Edit" with 0 or 2+ checked shows the info dialog instead of crashing.
7. "Delete" with groups checked removes them and re-saves `config/groups.json`.
8. "Login Facebook" opens a real, non-headless Chrome window under `browser/chrome_profile/`; a log line appears in the UI log panel.
9. "Stop" button is clickable at any time and does not crash the app even with no worker running.
10. Closing the window does not hang the process (daemon worker thread).

Do not run "Test 1 Group" / "Start Posting" against a real Facebook group as part of this automated plan — that requires a logged-in account and posts a real message; leave that as a manual acceptance step for the user once they've reviewed `SEL` in `src/selectors.py` against the live Facebook UI.

- [ ] **Step 4: Commit**

```bash
git add src/ui.py main.py
git commit -m "feat: add CustomTkinter desktop UI and app entry point"
```

---

### Task 9: `README.md`

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Facebook Rental Auto Poster

Tool nội bộ: đăng 1 bài viết (text + nhiều ảnh) lên nhiều Facebook Group,
dùng tài khoản Facebook thật qua Playwright + persistent Chrome profile
(không dùng Facebook Graph API).

## 1. Cài đặt

```bash
python3.12 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## 2. Đăng nhập Facebook lần đầu

```bash
python main.py
```

Bấm **Login Facebook** — cửa sổ Chrome thật sẽ mở (không headless). Đăng
nhập Facebook như bình thường trong cửa sổ đó. Phiên đăng nhập được lưu
tại `browser/chrome_profile/` — các lần chạy sau không cần đăng nhập lại.

## 3. Thêm Group

Bên phải, bấm **Add Group**, nhập tên + URL group
(`https://facebook.com/groups/...`). Có thể **Import JSON** để nạp hàng
loạt group theo định dạng `config/groups.json`:

```json
[
  {"name": "Cho thuê trọ Hà Nội", "url": "https://facebook.com/groups/xxxxx"}
]
```

## 4. Thêm ảnh + nội dung bài đăng

Bên trái, sửa nội dung trong ô textbox (có thể dùng `{group_name}` để tự
điền tên group vào nội dung khi đăng). Bấm **Add Images** để chọn nhiều
ảnh — hiển thị dạng thumbnail, chọn 1 ảnh rồi bấm **Remove** để bỏ.

## 5. Đăng bài

- Tick chọn các group muốn đăng ở bảng bên phải.
- **Test 1 Group**: chạy thử toàn bộ luồng trên đúng 1 group đang chọn.
- **Start Posting**: đăng lần lượt lên tất cả group đã chọn, có delay
  ngẫu nhiên (Min–Max giây) giữa các group, tự retry group lỗi (tối đa 2
  lần, đẩy xuống cuối hàng đợi) trước khi đánh dấu Failed hẳn.
- **Stop**: dừng giữa chừng bất kỳ lúc nào.
- Theo dõi tiến độ ("X / Y Groups") và log realtime (xanh = thành công,
  đỏ = lỗi, cam = pending/không chắc chắn) ngay trong app.
- Kết quả chi tiết từng group được ghi vào `logs/YYYY-MM-DD.csv` và log
  đầy đủ (kèm traceback nếu lỗi) tại `logs/app.log`.

## Lưu ý

- Facebook thay đổi giao diện thường xuyên — nếu tool không tìm thấy nút
  bấm, mở `src/selectors.py` và cập nhật lại theo aria-label/role hiện tại
  của Facebook.
- Đây là tool cá nhân, dùng tài khoản thật — dùng đúng mức, tránh spam
  gây khoá tài khoản.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and usage instructions"
```
