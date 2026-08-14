# Facebook Rental Auto Poster — Design Spec

Date: 2026-08-14
Status: Approved for implementation

## Mục tiêu

Tool nội bộ chạy trên máy cá nhân, dùng tài khoản Facebook thật của user, tự
động đăng 1 bài viết (text + nhiều ảnh) lên nhiều Facebook Group được chỉ
định. Không dùng Facebook Graph API — điều khiển trình duyệt thật qua
Playwright với persistent Chrome profile (đăng nhập 1 lần, dùng lại).

## Tech stack

- Python 3.12
- Playwright (Chromium, persistent context, không headless)
- CustomTkinter (desktop UI)
- Pillow (thumbnail ảnh)
- pandas (đọc/ghi CSV log)
- asyncio (chạy flow Playwright trong thread riêng)

## Cấu trúc project

```
facebook_auto_poster/
    main.py

    config/
        groups.json
        post.json

    assets/
        images/

    browser/
        chrome_profile/

    logs/

    src/
        ui.py
        poster.py
        browser.py
        logger.py
        config.py
```

## 1. Kiến trúc tổng thể (UI thread ↔ Worker thread)

- **UI thread**: CustomTkinter mainloop (`src/ui.py`). Chỉ build widget và
  đọc/ghi state qua `queue.Queue`. Không bao giờ gọi Playwright trực tiếp.
- **Worker thread**: khi bấm Login / Test 1 Group / Start Posting, spawn 1
  `threading.Thread` chạy `asyncio.run(poster_coroutine())`. Playwright
  context sống toàn bộ vòng đời trong thread này.
- **UI → Worker**: tham số truyền lúc spawn thread (list group đã chọn,
  content, delay range) + 1 `threading.Event` dùng làm stop flag, được check
  ở đầu mỗi vòng lặp group trong worker.
- **Worker → UI**: mọi log line / progress update / trạng thái group được
  đẩy vào 1 `queue.Queue` dùng chung. UI poll queue bằng
  `self.after(100, self._drain_queue)`, không bao giờ block chờ worker.
- Không dùng thư viện tích hợp asyncio-vào-Tkinter (VD qasync) — giữ 2 world
  tách biệt hoàn toàn qua queue, tránh phụ thuộc ngoài không cần thiết.

## 2. Module chia việc

- `src/config.py` — load/save `groups.json`, `post.json`; dataclass
  `Group(name, url)` và `PostConfig(content, images)`; validate cơ bản
  (url không rỗng, ảnh tồn tại trên đĩa).
- `src/browser.py` — quản lý lifecycle browser: `launch_persistent_context()`
  trỏ vào `browser/chrome_profile`, `get_page()`, `close()`. Không chứa logic
  nghiệp vụ đăng bài.
- `src/poster.py` — `PosterService`, orchestrate flow cho từng group, gọi
  các hàm selector-action tách riêng:
  - `open_group(page, url) -> None`
  - `create_post(page, content) -> None`
  - `upload_images(page, image_paths) -> None`
  - `publish(page) -> None`
  - `detect_result(page, content) -> ResultStatus` (`SUCCESS|FAILED|UNKNOWN`)
  - Mỗi hàm raise exception domain riêng khi lỗi thay vì return bool mập mờ.
- `src/logger.py` — setup `logging` chuẩn Python: console handler + file
  handler (`logs/app.log`, có traceback) + `QueueHandler` custom bắn log
  line (kèm level) vào `queue.Queue` cho UI; đồng thời ghi CSV
  `logs/YYYY-MM-DD.csv` mỗi khi 1 group kết thúc xử lý.
- `src/ui.py` — toàn bộ CustomTkinter widget, layout 2 cột, spawn/join
  worker thread, drain queue.

## 3. Selector strategy

Ưu tiên `page.get_by_role()`, `get_by_label()`, `get_by_text()` (aria-label
ổn định hơn class CSS random của Facebook). Toàn bộ selector định nghĩa
tập trung ở đầu `poster.py` (hoặc `src/selectors.py` nếu file dài), tách
biệt khỏi logic flow, để dễ sửa khi Facebook đổi UI mà không đụng logic
orchestration.

## 4. Data flow — Post content với placeholder động

`post.json`:
```json
{
  "content": "Cho thuê phòng trọ khu vực {group_name}...\n...",
  "images": ["assets/images/a.jpg", "assets/images/b.jpg"]
}
```

- Trước khi paste vào từng group, `poster.py` format lại content bằng
  `content.format(group_name=group.name)` (dùng `string.Template` hoặc
  `.format` với `defaultdict`-safe để content không chứa `{group_name}` vẫn
  chạy bình thường, không raise `KeyError`).
- 1 file `post.json` dùng chung cho toàn bộ group đã chọn trong 1 lần chạy
  — không có content riêng lẻ theo từng group ngoài placeholder.

`groups.json`:
```json
[
  {"name": "Cho thuê trọ Hà Nội", "url": "https://facebook.com/groups/xxxxx"}
]
```

## 5. Queue & Retry (đẩy fail xuống cuối hàng đợi)

- `PosterService` giữ 1 `deque[GroupTask]`, mỗi `GroupTask` có
  `group`, `attempts` (bắt đầu 0).
- Group fail (exception hoặc `detect_result() == FAILED`):
  `attempts += 1`; nếu `attempts < 2` → append lại vào **cuối** deque (không
  retry ngay lập tức, tiếp tục group khác trước); nếu `attempts >= 2` →
  đánh dấu FAILED chung cuộc, ghi CSV, không đẩy lại.
- Progress bar đếm theo số group **unique** đã có kết quả cuối cùng
  (Success/Failed), không đếm số lượt thử — hiển thị dạng "7 / 32 Groups".
- Stop: `threading.Event.set()` khi bấm Stop; worker check event ở đầu mỗi
  vòng lặp lấy task tiếp theo từ deque, dừng ngay, group đang chờ retry
  không bị mất (chỉ đơn giản không xử lý tiếp), log "Stopped by user".

## 6. detect_result() — multi-signal, có trạng thái UNKNOWN

Trả về `SUCCESS | FAILED | UNKNOWN`. Check tuần tự, mỗi bước dùng
`wait_for_*` với timeout ngắn:

1. Dialog composer (`get_by_role("dialog")`) đã đóng / biến mất.
2. Không còn nút Publish/Post ở trạng thái loading/disabled kẹt lại.
3. (tuỳ chọn, bật/tắt qua config) reload đầu feed group, tìm bài mới nhất
   khớp vài từ đầu của content đã đăng → nếu thấy, chắc chắn `SUCCESS`.

Nếu bước 1+2 pass nhưng bước 3 không xác nhận được (hoặc bị tắt) →
`UNKNOWN`. `UNKNOWN` log màu cam riêng biệt (khác Success/Error), **không**
tính vào retry logic (coi như khả năng đã đăng thành công, tránh đăng
trùng lặp), nhưng cũng không tính là Success trong progress — ghi CSV với
status `UNKNOWN` để user tự kiểm tra thủ công.

## 7. Error handling

- Mỗi hàm action (`open_group`, `create_post`, `upload_images`, `publish`)
  raise exception domain riêng (`GroupNotFoundError`, `UploadTimeoutError`,
  `PublishError`, ...). `PosterService` catch theo loại, map ra message log
  người-đọc-được thay vì traceback thô hiển thị lên UI.
- Exception không lường trước (crash lạ) → catch chung ở vòng loop group,
  log ERROR đầy đủ traceback vào `logs/app.log`, đánh dấu group đó FAILED,
  tiếp tục group kế tiếp — không crash toàn app.

## 8. Logging

- `logging` chuẩn Python → console + `logs/app.log` (debug chi tiết, có
  traceback).
- `logs/YYYY-MM-DD.csv` — cột `time, group, status, message` — append mỗi
  khi 1 group có kết quả cuối cùng (SUCCESS/FAILED/UNKNOWN).
- `QueueHandler` custom bắn từng log line (kèm level/màu) vào
  `queue.Queue` để UI hiển thị realtime: Xanh=Success, Đỏ=Error,
  Cam=Pending/Unknown.

## 9. UI

Tông trắng + xanh dương, ~1100x700, 2 cột.

**Trái**: nội dung bài (textbox load/edit `post.json`), danh sách ảnh
(thumbnail + Add/Remove, multi-select), delay min/max (giây).

**Phải**: bảng group (checkbox, tên, url) + Add/Edit/Delete/Import JSON;
control (Login Facebook / Test 1 Group / Start Posting / Stop); progress
bar "X / Y Groups"; log realtime màu theo status.

## 10. Testing

- Nút "Test 1 Group": chạy full flow (open→create→upload→publish→detect)
  trên đúng 1 group user đang chọn, dùng chung code path với Start Posting
  (không viết luồng riêng).
- Không viết Playwright automated test (phụ thuộc UI Facebook sống, dễ
  gãy liên tục, không đáng đầu tư). `poster.py` viết theo dạng nhận `Page`
  làm tham số, để lại khả năng viết unit test mock `Page` sau này nếu cần
  — ngoài scope hiện tại.

## Ngoài scope (không làm)

- Không dùng Facebook Graph API.
- Không đóng gói .exe/binary — chạy trực tiếp `python main.py` trong venv.
- Không content riêng biệt hoàn toàn theo từng group (chỉ hỗ trợ 1
  placeholder `{group_name}`).
- Không scheduling (đăng theo giờ hẹn) — chạy thủ công khi bấm Start.
