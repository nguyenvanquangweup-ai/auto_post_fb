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
    assert data == [{"name": "A", "url": "https://facebook.com/groups/1", "anonymous": False}]


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
