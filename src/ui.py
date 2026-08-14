from __future__ import annotations

import asyncio
import queue
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable, Coroutine

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
    def __init__(self, master: ctk.CTk, title: str, name: str = "", url: str = "") -> None:
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

    def _on_save(self) -> None:
        name = self.name_entry.get().strip()
        url = self.url_entry.get().strip()
        if not name or not url:
            messagebox.showerror("Lỗi", "Tên và URL không được để trống")
            return
        self.result = (name, url)
        self.destroy()


class App(ctk.CTk):
    def __init__(self, base_dir: Path) -> None:
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

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self)
        left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        right = ctk.CTkFrame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)

        self._build_left_panel(left)
        self._build_right_panel(right)

    def _build_left_panel(self, parent: ctk.CTkFrame) -> None:
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

    def _build_right_panel(self, parent: ctk.CTkFrame) -> None:
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

    def _load_initial_config(self) -> None:
        try:
            self.groups = load_groups(self.groups_path)
        except Exception as exc:
            self.logger.warning(f"Không tải được {self.groups_path.name}: {exc}")
            self.groups = []
        self._refresh_group_table()

        try:
            post = load_post_config(self.post_path)
        except Exception as exc:
            self.logger.warning(f"Không tải được {self.post_path.name}: {exc}")
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

    def _refresh_group_table(self) -> None:
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

    def _add_group(self) -> None:
        dialog = GroupDialog(self, "Add Group")
        self.wait_window(dialog)
        if dialog.result:
            name, url = dialog.result
            self.groups.append(Group(name=name, url=url))
            save_groups(self.groups_path, self.groups)
            self._refresh_group_table()

    def _edit_group(self) -> None:
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

    def _delete_group(self) -> None:
        selected = {i for i, v in enumerate(self.group_vars) if v.get()}
        if not selected:
            messagebox.showinfo("Delete Group", "Chọn ít nhất 1 group để xoá")
            return
        self.groups = [g for i, g in enumerate(self.groups) if i not in selected]
        save_groups(self.groups_path, self.groups)
        self._refresh_group_table()

    def _import_groups_json(self) -> None:
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

    def _add_images(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=[("Images", "*.jpg *.jpeg *.png")])
        self.image_paths.extend(paths)
        self._refresh_image_list()

    def _remove_selected_image(self) -> None:
        if self.selected_image_index is None:
            return
        del self.image_paths[self.selected_image_index]
        self.selected_image_index = None
        self._refresh_image_list()

    def _refresh_image_list(self) -> None:
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

    def _select_image(self, idx: int) -> None:
        self.selected_image_index = idx

    # ---------- realtime log + progress ----------

    def _drain_log_queue(self) -> None:
        try:
            while True:
                level, message = self.log_queue.get_nowait()
                self._append_log(level, message)
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    def _append_log(self, level: str, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        tag = f"tag_{level}"
        line_start = self.log_box.index("end-2l")
        line_end = self.log_box.index("end-1l")
        self.log_box.tag_config(tag, foreground=LOG_COLORS.get(level, "#1f2328"))
        self.log_box.tag_add(tag, line_start, line_end)
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _drain_progress_queue(self) -> None:
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

    def _on_login(self) -> None:
        self._run_in_worker(self._login_flow)

    def _prepare_post_args(self) -> tuple[str, list[str], float, float] | None:
        # Reads content/delay widgets and saves config on the UI thread only —
        # _post_flow (worker thread) must never touch Tkinter widgets directly.
        post = self._save_current_post_config()
        missing = validate_post_config(post, self.base_dir)
        if missing:
            self.logger.error(f"Thiếu ảnh: {', '.join(missing)}")
            return None
        min_delay, max_delay = self._read_delays()
        return post.content, list(post.images), min_delay, max_delay

    def _on_test_one(self) -> None:
        selected = self._selected_groups()
        if not selected:
            messagebox.showinfo("Test 1 Group", "Chọn 1 group để test")
            return
        args = self._prepare_post_args()
        if args is None:
            return
        content, images, min_delay, max_delay = args
        self._run_in_worker(lambda: self._post_flow([selected[0]], content, images, min_delay, max_delay))

    def _on_start(self) -> None:
        selected = self._selected_groups()
        if not selected:
            messagebox.showinfo("Start Posting", "Chọn ít nhất 1 group")
            return
        args = self._prepare_post_args()
        if args is None:
            return
        content, images, min_delay, max_delay = args
        self._run_in_worker(lambda: self._post_flow(selected, content, images, min_delay, max_delay))

    def _on_stop(self) -> None:
        self.stop_event.set()

    def _run_in_worker(self, coro_factory: Callable[[], Coroutine[Any, Any, None]]) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Đang chạy", "Đang có tác vụ chạy, chờ hoàn thành hoặc bấm Stop")
            return
        self.stop_event = threading.Event()

        def target() -> None:
            try:
                asyncio.run(coro_factory())
            except Exception as exc:
                self.logger.error(f"Lỗi worker: {exc}")

        self.worker_thread = threading.Thread(target=target, daemon=True)
        self.worker_thread.start()

    async def _login_flow(self) -> None:
        browser = BrowserManager(self.profile_dir)
        await browser.launch()
        self.logger.info("Đã mở Chrome. Đăng nhập Facebook nếu cần, cửa sổ này giữ nguyên phiên đăng nhập cho lần sau.")

    async def _post_flow(
        self, groups: list[Group], content: str, images: list[str], min_delay: float, max_delay: float
    ) -> None:
        config = PosterConfig(min_delay=min_delay, max_delay=max_delay, verify_feed=False)
        csv_path = self.logs_dir / f"{time.strftime('%Y-%m-%d')}.csv"

        def csv_writer(group_name: str, status: str, message: str) -> None:
            write_csv_result(csv_path, time.strftime("%Y-%m-%d %H:%M:%S"), group_name, status, message)

        service = PosterService(config, self.logger, csv_writer)
        self.progress_queue.put((0, len(groups)))

        browser = BrowserManager(self.profile_dir)
        await browser.launch()
        page = await browser.get_page()
        try:
            await service.run(
                page, groups, content, images, self.stop_event,
                on_progress=lambda d, t: self.progress_queue.put((d, t)),
            )
        finally:
            await browser.close()
