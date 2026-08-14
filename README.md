# Facebook Rental Auto Poster

Tool nội bộ: đăng 1 bài viết (text + nhiều ảnh) lên nhiều Facebook Group,
dùng tài khoản Facebook thật qua Playwright + persistent Chrome profile
(không dùng Facebook Graph API).

## 1. Cài đặt

**Linux / macOS:**

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
playwright install-deps chromium  # cài thư viện hệ thống cho Chromium (vd: libnspr4, libnss3)
```

**Windows:**

Kiểm tra Python đã cài: `py -0`. Nếu chưa có Python 3.12, tải tại
https://www.python.org/downloads/ (nhớ tick "Add python.exe to PATH"), hoặc
dùng bản Python khác đã có sẵn (3.12+ đều chạy được, không cần đúng bản).

```cmd
py -3.12 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Nếu dùng conda, tạo env riêng thay vì `venv`:

```cmd
conda create -n fbpost python=3.12 -y
conda activate fbpost
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
ảnh — hiển thị dạng thumbnail, bấm nút **✕** trên từng ảnh để xoá riêng ảnh đó.

## 5. Đăng bài

- Tick chọn các group muốn đăng ở bảng bên phải.
- **Test 1 Group**: chạy thử toàn bộ luồng trên đúng 1 group đang chọn.
- **Start Posting**: đăng lần lượt lên tất cả group đã chọn, có delay
  ngẫu nhiên (Min–Max giây) giữa các group, tự retry group lỗi (tối đa 2
  lần, đẩy xuống cuối hàng đợi) trước khi đánh dấu Failed hẳn.
- **Stop**: dừng giữa chừng bất kỳ lúc nào.
- Tick **Đăng ẩn danh** nếu muốn đăng ẩn danh — group nào không hỗ trợ
  chế độ này sẽ tự động đăng công khai và có log cảnh báo (màu cam) để
  bạn biết group đó không ẩn danh được.
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
