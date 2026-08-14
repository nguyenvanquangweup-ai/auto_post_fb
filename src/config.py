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
