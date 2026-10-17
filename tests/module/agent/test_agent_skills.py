"""Agent 技能包：目录解析、按需加载与提示词注入。"""

from __future__ import annotations

from pathlib import Path

import pytest

from module.Agent.AgentPromptBuilder import _render_skills_catalog
from module.Agent.tools import skill_tools


def test_skill_catalog_lists_bundled_skills() -> None:
    metas = skill_tools._iter_skill_metas()

    names = [meta.name for meta in metas]
    assert names == sorted(names)
    # 内置技能包必须全部带描述，否则不会出现在系统提示的目录里。
    for meta in metas:
        assert meta.description
    assert {
        "renpy-pipeline",
        "glossary",
        "text-preserve",
        "rpy-syntax",
        "proofreading",
    } <= set(names)


def test_read_skill_returns_body_without_front_matter() -> None:
    result = skill_tools.read_skill(name = "renpy-pipeline")

    assert result.success is True
    content = result.data["content"]
    assert content.startswith("# Ren'Py 汉化流水线")
    assert "name: renpy-pipeline" not in content
    assert result.data["truncated"] is False


def test_read_skill_rejects_unknown_skill() -> None:
    result = skill_tools.read_skill(name = "no-such-skill")

    assert result.success is False
    assert result.code == "SKILL_NOT_FOUND"


@pytest.mark.parametrize(
    "name",
    [
        "",
        "../secrets",
        "skills/renpy-pipeline",
        "Renpy-Pipeline",
        "renpy_pipeline",
        "renpy-pipeline/../../etc",
    ],
)
def test_read_skill_rejects_invalid_names(name: str) -> None:
    result = skill_tools.read_skill(name = name)

    assert result.success is False
    assert result.code == "SKILL_NAME_INVALID"


def test_read_skill_truncates_long_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_dir = tmp_path / "big-skill"
    skill_dir.mkdir()
    body = "\n".join(f"第 {index} 行规则" for index in range(4000))
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: big-skill\ndescription: 超长技能\n---\n\n{body}",
        encoding = "utf-8",
    )
    monkeypatch.setattr(skill_tools, "SKILLS_DIR", tmp_path)

    result = skill_tools.read_skill(name = "big-skill")

    assert result.success is True
    assert result.data["truncated"] is True
    assert len(result.data["content"]) == skill_tools.MAX_SKILL_CHARS


def test_skills_catalog_is_injected_into_prompt() -> None:
    catalog = _render_skills_catalog()

    assert "renpy-pipeline" in catalog
    assert "read_skill" in catalog


def test_skills_catalog_skips_entries_without_description(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good = tmp_path / "good-skill"
    good.mkdir()
    (good / "SKILL.md").write_text(
        "---\nname: good-skill\ndescription: 可用\n---\n\n正文",
        encoding = "utf-8",
    )
    bad = tmp_path / "bad-skill"
    bad.mkdir()
    (bad / "SKILL.md").write_text("没有 Front Matter 的正文", encoding = "utf-8")
    monkeypatch.setattr(skill_tools, "SKILLS_DIR", tmp_path)

    metas = skill_tools._iter_skill_metas()

    assert [meta.name for meta in metas] == ["good-skill"]
