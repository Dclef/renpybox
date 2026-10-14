"""语言入口与默认语言：真实资源落盘、语言名与路径边界。"""
from __future__ import annotations

import ast
import subprocess
import textwrap
from pathlib import Path

import pytest

from base.PathHelper import get_resource_path
from module.Tool.LanguageTools import (
    DEFAULT_SCRIPT_NAME,
    HOOK_NAME,
    LanguageToolsError,
    describe_project,
    install_default_language,
    install_language_entrance,
    parse_default_language,
)


def make_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "Demo"
    game = project / "game"
    for name in ("chinese", "schinese", "tchinese", "chinese_new", "none", "Foo_Filtered_Suspicious"):
        (game / "tl" / name).mkdir(parents=True)
    (game / "script.rpy").write_text('label start:\n    "hi"\n', encoding="utf-8")
    return project, game


def make_junction(link: Path, target: Path) -> None:
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not link.exists():
        pytest.skip(f"无法创建目录联接: {completed.stderr or completed.stdout}")


def test_entrance_and_default_match_real_resources(tmp_path):
    project, game = make_project(tmp_path)
    entrance = install_language_entrance(project)
    assert entrance["written"] is True
    assert Path(entrance["path"]) == game / HOOK_NAME
    hook_source = Path(get_resource_path("resource", "hooks", HOOK_NAME))
    assert (game / HOOK_NAME).read_text(encoding="utf-8-sig").splitlines() == hook_source.read_text(encoding="utf-8-sig").splitlines()

    installed = install_default_language(game, "schinese")
    script_path = game / DEFAULT_SCRIPT_NAME
    assert Path(installed["path"]) == script_path
    assert installed["language"] == "schinese"
    template = Path(get_resource_path("resource", "templates", "default_langauge_template.txt"))
    expected = template.read_text(encoding="utf-8-sig").replace("{tl_name}", "schinese")
    text = script_path.read_text(encoding="utf-8-sig")
    assert text.splitlines() == expected.splitlines()
    body = textwrap.dedent("\n".join(text.splitlines()[1:]))
    tree = ast.parse(body)
    assert len(tree.body) == 1
    assert isinstance(tree.body[0], ast.Assign)
    assert tree.body[0].value.value == "schinese"
    described = describe_project(project)
    assert described["languages"] == ["chinese", "schinese", "tchinese"]
    assert described["entrance_exists"] is True
    assert described["default_language"] == "schinese"
    assert not list(game.glob("*.py")) and not list(game.glob("*.bak"))


@pytest.mark.parametrize("language", [
    "", " ", "schinese ", " schinese", ".", "..", "../evil", "..\\evil", "a/b", "a\\b",
    'chi"nese', "chi'nese", "a\nb", "a\rb", "CON", "con", "LPT1", "NUL",
    "chinese_new", "tchinese_new", "Foo_New", "none", "tl", "game", "tchinese.", "C:evil", "x\x00y",
])
def test_invalid_language_is_rejected_without_rewrite(tmp_path, language):
    project, game = make_project(tmp_path)
    with pytest.raises(LanguageToolsError, match="语言名无效"):
        install_default_language(project, language)
    assert not (game / DEFAULT_SCRIPT_NAME).exists()


def test_missing_tl_resource_and_empty_project(tmp_path, monkeypatch):
    project, game = make_project(tmp_path)
    with pytest.raises(LanguageToolsError, match="找不到翻译目录"):
        install_default_language(project, "japanese")
    assert not (game / DEFAULT_SCRIPT_NAME).exists()

    monkeypatch.setattr(
        "module.Tool.LanguageTools.get_resource_path",
        lambda *parts: str(tmp_path / "missing-resource"),
    )
    with pytest.raises(LanguageToolsError, match="资源缺失"):
        install_language_entrance(project)
    assert not (game / HOOK_NAME).exists()
    with pytest.raises(LanguageToolsError):
        install_language_entrance("")
    empty = tmp_path / "empty-dir"
    empty.mkdir()
    with pytest.raises(LanguageToolsError, match="找不到 game 目录"):
        install_language_entrance(empty)


def test_directory_target_and_escaping_links_are_rejected(tmp_path):
    project, game = make_project(tmp_path)
    directory_target = game / HOOK_NAME
    directory_target.mkdir()
    with pytest.raises(LanguageToolsError, match="目录"):
        install_language_entrance(project)
    assert directory_target.is_dir()

    outside = tmp_path / "outside"
    (outside / "tl" / "chinese").mkdir(parents=True)
    (outside / "secret.txt").write_text("保留", encoding="utf-8")
    linked_project = tmp_path / "linked"
    linked_project.mkdir()
    make_junction(linked_project / "game", outside)
    with pytest.raises(LanguageToolsError, match="越出"):
        install_language_entrance(linked_project)
    assert not (outside / HOOK_NAME).exists()
    assert (outside / "secret.txt").read_text(encoding="utf-8") == "保留"

    escaped_language = tmp_path / "escaped-language"
    escaped_language.mkdir()
    make_junction(game / "tl" / "escaped", escaped_language)
    assert "escaped" not in describe_project(project)["languages"]


def test_file_symlink_target_is_rejected(tmp_path):
    project, game = make_project(tmp_path)
    outside = tmp_path / "outside-file.rpy"
    outside.write_text("外部文件", encoding="utf-8")
    link = game / DEFAULT_SCRIPT_NAME
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"无法创建文件符号链接: {exc}")
    with pytest.raises(LanguageToolsError, match="越出"):
        install_default_language(project, "schinese")
    assert outside.read_text(encoding="utf-8") == "外部文件"


def test_failed_replace_keeps_old_file_and_skips_game_backup(tmp_path, monkeypatch):
    project, game = make_project(tmp_path)
    target = game / HOOK_NAME
    target.write_text("旧钩子", encoding="utf-8")

    def fail_replace(src, dst):
        raise OSError("磁盘写入失败")

    monkeypatch.setattr("module.File.AtomicWrite.os.replace", fail_replace)
    with pytest.raises(LanguageToolsError, match="原文件已保留"):
        install_language_entrance(project)
    assert target.read_text(encoding="utf-8") == "旧钩子"
    assert not [path for path in game.iterdir() if path.name.endswith(".tmp") or path.suffix in {".bak", ".py"}]


def test_parser_reads_assignment_and_does_not_execute(tmp_path):
    marker = tmp_path / "pwned.txt"
    malicious = (
        'init 1000 python:\n'
        '    renpy.game.preferences.language = "schinese"\n'
        "    import pathlib\n"
        f"    pathlib.Path({str(marker)!r}).write_text('x')\n"
    )
    assert parse_default_language(malicious) is None
    assert not marker.exists()
    safe = 'init 1000 python:\n    renpy.game.preferences.language = "tchinese"\n'
    assert parse_default_language(safe) == "tchinese"


def test_crlf_hook_preserves_original_line_endings(tmp_path, monkeypatch):
    """Windows 检出的 CRLF 资源不能被二次转换成 CRCRLF。"""
    project, game = make_project(tmp_path)
    resource = tmp_path / "hook.rpy"
    content = b'init python:\r\n    language = "chinese"\r\n'
    resource.write_bytes(content)
    monkeypatch.setattr("module.Tool.LanguageTools.get_resource_path", lambda *parts: str(resource))
    install_language_entrance(project)
    assert (game / HOOK_NAME).read_bytes() == content
