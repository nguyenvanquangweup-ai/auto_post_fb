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
- Mỗi group trong bảng có checkbox **Ẩn danh** riêng — tick group nào
  thì group đó đăng ẩn danh (lưu theo group, không cần tick lại mỗi
  lần). Group nào không hỗ trợ chế độ này sẽ tự động đăng công khai và
  có log cảnh báo (màu cam) để bạn biết group đó không ẩn danh được.
- Bấm **Kiểm tra ẩn danh** (đã tick chọn group) để dò trước group nào hỗ
  trợ đăng ẩn danh — kết quả hiện dấu **✓** (hỗ trợ) hoặc **✗** (không hỗ
  trợ, checkbox Ẩn danh bị khoá) ngay trong bảng, lưu lại cho các lần
  đăng sau.
- Checkbox **"Xác nhận đăng thành công (reload feed)"** (panel trái, dưới
  Delay): không tick thì chỉ kiểm tra composer đã đóng + nút Đăng biến
  mất, ghi kết quả là **UNKNOWN** (không chắc chắn); tick lên thì sau khi
  đăng sẽ reload lại trang group, tìm đoạn đầu nội dung vừa đăng trên
  feed để ghi **SUCCESS** thật. Verify này chỉ để ghi nhãn kết quả cho
  chính xác hơn — bài vẫn đã đăng lên FB bình thường dù verify không tìm
  thấy (feed đông bài mới có thể chưa kịp render), tool không đăng lại
  hay retry vì lý do này.
- Theo dõi tiến độ ("X / Y Groups") và log realtime (xanh = thành công,
  đỏ = lỗi, cam = pending/không chắc chắn) ngay trong app.
- Đăng xong (hoặc bấm Stop giữa chừng), 1 popup tự hiện liệt kê từng
  group: trạng thái (Thành công/Thất bại/Không chắc) + lý do lỗi nếu có,
  kèm dòng tổng "X/Y thành công" — không cần cuộn log để nắm tình hình.
- Kết quả chi tiết từng group được ghi vào `logs/YYYY-MM-DD.csv` và log
  đầy đủ (kèm traceback nếu lỗi) tại `logs/app.log`.

## Lưu ý

- Facebook thay đổi giao diện thường xuyên — nếu tool không tìm thấy nút
  bấm, mở `src/selectors.py` và cập nhật lại theo aria-label/role hiện tại
  của Facebook.
- Đây là tool cá nhân, dùng tài khoản thật — dùng đúng mức, tránh spam
  gây khoá tài khoản.
