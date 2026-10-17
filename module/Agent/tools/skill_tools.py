"""Agent 技能包工具：列出技能目录、按需加载技能正文。

技能只是领域知识，不提供任何新的文件系统或命令执行能力；路径必须在
``module/Agent/skills`` 之内，技能名走白名单字符，杜绝路径穿越。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from module.Localizer.Localizer import Localizer

from ..types import ToolResult


SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
SKILL_FILE_NAME = "SKILL.md"
MAX_SKILL_CHARS = 12_000
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")

_FRONT_MATTER_DELIMITER = "---"


@dataclass(frozen=True)
class SkillMeta:
    """技能目录条目：只含名字与描述，不含正文。"""

    name: str
    description: str
    path: Path


def _parse_front_matter(text: str) -> dict[str, str]:
    """解析 ``---`` 包围的简单 Front Matter，只取一级 key: value。"""

    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONT_MATTER_DELIMITER:
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == _FRONT_MATTER_DELIMITER:
            break
        key, separator, value = line.partition(":")
        if not separator:
            continue
        fields[key.strip()] = value.strip().strip("\"'")
    return fields


def _strip_front_matter(text: str) -> str:
    """去掉 Front Matter，只留正文，避免模型重复看到元数据。"""

    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONT_MATTER_DELIMITER:
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == _FRONT_MATTER_DELIMITER:
            return "\n".join(lines[index + 1 :]).lstrip("\n")
    return text


def _iter_skill_metas() -> list[SkillMeta]:
    """按名字排序返回可用技能；目录缺失或条目损坏时静默跳过。"""

    if not SKILLS_DIR.is_dir():
        return []
    metas: list[SkillMeta] = []
    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir() or not SKILL_NAME_PATTERN.fullmatch(entry.name):
            continue
        skill_file = entry / SKILL_FILE_NAME
        if not skill_file.is_file():
            continue
        try:
            text = skill_file.read_text(encoding="utf-8")
        except OSError:
            continue
        fields = _parse_front_matter(text)
        description = fields.get("description", "").strip()
        if not description:
            continue
        metas.append(
            SkillMeta(
                name=fields.get("name", "").strip() or entry.name,
                description=description,
                path=skill_file,
            )
        )
    return metas


def list_skills() -> ToolResult:
    """列出可用技能的名字与用途描述，不返回正文。"""

    localizer = Localizer.get()
    metas = _iter_skill_metas()
    if not metas:
        return ToolResult(True, localizer.agent_skill_list_empty, data={"skills": []})

    skills: list[dict[str, Any]] = [
        {"name": meta.name, "description": meta.description} for meta in metas
    ]
    return ToolResult(
        True,
        localizer.agent_skill_list_ready.format(count=len(skills)),
        data={"skills": skills},
    )


def read_skill(name: str | None = None, **_: Any) -> ToolResult:
    """加载指定技能正文；超长时截断并提示分段。"""

    localizer = Localizer.get()
    skill_name = str(name or "").strip()
    if not SKILL_NAME_PATTERN.fullmatch(skill_name):
        return ToolResult(
            False,
            localizer.agent_skill_name_invalid.format(name=skill_name),
            code="SKILL_NAME_INVALID",
        )

    root = SKILLS_DIR.resolve()
    skill_file = (root / skill_name / SKILL_FILE_NAME).resolve()
    if skill_file.parent.parent != root or not skill_file.is_file():
        return ToolResult(
            False,
            localizer.agent_skill_not_found.format(name=skill_name),
            code="SKILL_NOT_FOUND",
        )

    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError:
        return ToolResult(
            False,
            localizer.agent_skill_read_failed.format(name=skill_name),
            code="SKILL_READ_FAILED",
        )

    body = _strip_front_matter(text).strip()
    truncated = len(body) > MAX_SKILL_CHARS
    if truncated:
        body = body[:MAX_SKILL_CHARS]

    message = localizer.agent_skill_loaded.format(name=skill_name)
    if truncated:
        message = localizer.agent_skill_truncated_hint.format(
            name=skill_name,
            count=len(body),
        )
    return ToolResult(
        True,
        message,
        data={"name": skill_name, "content": body, "truncated": truncated},
    )


__all__ = ["list_skills", "read_skill", "SKILLS_DIR", "MAX_SKILL_CHARS"]
