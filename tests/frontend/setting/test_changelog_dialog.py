import frontend.Setting.ChangelogDialog as changelog_dialog
from base.VersionManager import VersionManager
from frontend.Setting.ChangelogDialog import build_changelog_markdown
from frontend.Setting.ChangelogDialog import changelog_to_html
from frontend.Setting.ChangelogDialog import extract_version_section
from frontend.Setting.ChangelogDialog import read_local_changelog
from module.Localizer.Localizer import Localizer


def test_extract_version_section_returns_only_requested_release():
    markdown = """# 更新日志

## v0.7.2 - 2026-07-31
### 修复
- 新版修复

## v0.7.1 - 2026-07-26
### 新增
- 旧版功能
"""

    section = extract_version_section(markdown, "v0.7.2")

    assert section.startswith("## v0.7.2")
    assert "新版修复" in section
    assert "v0.7.1" not in section


def test_extract_version_section_accepts_version_without_v_prefix():
    assert "当前版本" in extract_version_section(
        "## v1.2.3\n- 当前版本\n\n## v1.2.2\n- 上个版本",
        "1.2.3",
    )


def test_extract_version_section_returns_empty_for_missing_release():
    assert extract_version_section("## v1.2.3\n- 内容", "v9.9.9") == ""


def test_read_local_changelog_works_in_source_tree():
    assert read_local_changelog().startswith("# 更新日志")


def test_remote_release_notes_are_prepended(monkeypatch):
    monkeypatch.setattr(
        changelog_dialog,
        "read_local_changelog",
        lambda: "# 更新日志\n\n## v0.7.1\n- 本地记录",
    )

    markdown = build_changelog_markdown({
        "tag_name": "v99.0.0",
        "body": "- 远端记录",
    })

    assert markdown.index("可更新到 v99.0.0") < markdown.index("# 更新日志")
    assert "远端记录" in markdown


def test_current_only_missing_release_returns_empty(monkeypatch):
    monkeypatch.setattr(
        changelog_dialog,
        "read_local_changelog",
        lambda: "# 更新日志\n\n## v1.2.3\n- 已有版本",
    )

    assert build_changelog_markdown(current_only_version="v9.9.9") == ""


def test_manual_changelog_keeps_empty_state_feedback(monkeypatch):
    monkeypatch.setattr(changelog_dialog, "read_local_changelog", lambda: "")

    assert build_changelog_markdown() == Localizer.get().app_changelog_empty


def test_changelog_html_uses_controlled_hierarchy_and_inline_code():
    rendered = changelog_to_html(
        """# 更新日志

## v1.2.3 - 2026-07-31
### 修复
- 修复 `<路径>` 中的 `res/xml/backup.xml`
""",
        muted="#909090",
        code_bg="#F0F0F0",
    )

    assert "# 更新日志" not in rendered
    assert "font-size:11pt;font-weight:600" in rendered
    assert "v1.2.3 · 2026-07-31" in rendered
    assert "font-size:9pt;color:#909090" in rendered
    assert '<li style="font-size:10pt;margin-bottom:4px;">' in rendered
    assert "&lt;路径&gt;" in rendered
    assert "background-color:#F0F0F0" in rendered
    assert "font-family:Consolas,monospace" in rendered
    assert "&nbsp;res/xml/backup.xml&nbsp;" in rendered


def test_full_release_history_has_a_non_latest_url():
    assert VersionManager.RELEASES_URL.endswith("/releases")
    assert not VersionManager.RELEASES_URL.endswith("/latest")
