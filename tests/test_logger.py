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
