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
