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
