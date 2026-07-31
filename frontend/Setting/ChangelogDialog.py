from __future__ import annotations

import html as html_lib
import re
from pathlib import Path
from typing import Any

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QFrame, QWidget
from qfluentwidgets import (
    FluentIcon,
    MessageBoxBase,
    SubtitleLabel,
    TextBrowser,
    TransparentPushButton,
    isDarkTheme,
)

from base.PathHelper import get_resource_path
from base.Version import Version
from base.VersionManager import VersionManager
from module.Localizer.Localizer import Localizer


_VERSION_HEADING_RE = re.compile(
    r"^##\s+(v?\d+(?:\.\d+){2,3})(?:\s+-.*)?\s*$",
    re.IGNORECASE,
)


def read_local_changelog() -> str:
    candidates = (
        Path(get_resource_path("resource", "CHANGELOG.md")),
        Path(get_resource_path("CHANGELOG.md")),
    )
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return candidate.read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError):
            continue
    return ""


def extract_version_section(markdown: str, version: str) -> str:
    target = str(version).strip().lower().removeprefix("v")
    lines = str(markdown or "").splitlines()
    start = None
    for index, line in enumerate(lines):
        match = _VERSION_HEADING_RE.match(line.strip())
        if match and match.group(1).lower().removeprefix("v") == target:
            start = index
            break
    if start is None:
        return ""

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if _VERSION_HEADING_RE.match(lines[index].strip()):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def _inline_code(text: str, code_bg: str) -> str:
    """转义文本并把 `code` 渲染成带底色的等宽片段。"""
    out: list[str] = []
    for index, segment in enumerate(str(text).split("`")):
        escaped = html_lib.escape(segment)
        if index % 2 == 1:
            out.append(
                f'<span style="background-color:{code_bg};'
                f'font-family:Consolas,monospace;">&nbsp;{escaped}&nbsp;</span>'
            )
        else:
            out.append(escaped)
    return "".join(out)


def changelog_to_html(markdown: str, *, muted: str, code_bg: str) -> str:
    """把 CHANGELOG.md 渲染为受控排版的 HTML。

    Qt 的 setMarkdown 会写入内联字号，外部样式表压不住，因此这里自行拼装。
    """
    parts: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    for raw in str(markdown or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--"):
            continue

        if line in ("---", "***", "___"):
            # Markdown 分隔线，渲染成真的横线而不是字面量。
            close_list()
            parts.append(
                f'<div style="border-top:1px solid {muted};'
                f'margin-top:18px;margin-bottom:6px;"></div>'
            )
        elif line.startswith("## "):
            close_list()
            text = html_lib.escape(line[3:].strip()).replace(" - ", " · ")
            parts.append(
                f'<p style="font-size:11pt;font-weight:600;'
                f'margin-top:16px;margin-bottom:2px;">{text}</p>'
            )
        elif line.startswith("### "):
            close_list()
            text = html_lib.escape(line[4:].strip())
            parts.append(
                f'<p style="font-size:9pt;color:{muted};'
                f'margin-top:10px;margin-bottom:2px;">{text}</p>'
            )
        elif line.startswith("# "):
            continue
        elif line.startswith(("- ", "* ")):
            if not in_list:
                parts.append('<ul style="margin-top:2px;margin-left:-8px;">')
                in_list = True
            parts.append(
                f'<li style="font-size:10pt;margin-bottom:4px;">'
                f'{_inline_code(line[2:].strip(), code_bg)}</li>'
            )
        else:
            close_list()
            parts.append(
                f'<p style="font-size:10pt;margin-top:4px;">'
                f'{_inline_code(line, code_bg)}</p>'
            )

    close_list()
    return "".join(parts)


def build_changelog_markdown(
    latest: dict[str, Any] | None = None,
    current_only_version: str | None = None,
) -> str:
    strings = Localizer.get()
    local_markdown = read_local_changelog()
    if current_only_version:
        return extract_version_section(local_markdown, current_only_version)

    sections: list[str] = []
    release = dict(latest or {})
    latest_version = str(release.get("tag_name", "")).strip()
    if (
        latest_version
        and VersionManager.parse_version(Version.CURRENT)
        < VersionManager.parse_version(latest_version)
        # 本地 CHANGELOG.md 已收录该版本时不再追加远端说明，否则同一版本
        # 会连着出现两遍（发版时通常把 release body 抄进了 CHANGELOG）。
        and not extract_version_section(local_markdown, latest_version)
    ):
        heading = strings.app_changelog_available.replace(
            "{VERSION}", VersionManager.display_version(latest_version)
        )
        body = str(release.get("body", "")).strip() or strings.app_update_notes_empty
        sections.append(f"## {heading}\n\n{body}")

    if local_markdown:
        sections.append(local_markdown)
    return "\n\n---\n\n".join(sections) or strings.app_changelog_empty


class ChangelogDialog(MessageBoxBase):
    def __init__(
        self,
        parent: QWidget,
        latest: dict[str, Any] | None = None,
        current_only_version: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_ui(latest, current_only_version)

    def _init_ui(
        self,
        latest: dict[str, Any] | None,
        current_only_version: str | None,
    ) -> None:
        strings = Localizer.get()
        self.widget.setMinimumWidth(720)
        self.viewLayout.setContentsMargins(24, 20, 24, 8)
        self.viewLayout.setSpacing(16)
        self.viewLayout.addWidget(SubtitleLabel(strings.app_changelog_title, self.widget))

        self.browser = TextBrowser(self.widget)
        self.browser.setReadOnly(True)
        self.browser.setOpenExternalLinks(True)
        self.browser.setFrameShape(QFrame.NoFrame)
        self.browser.setStyleSheet(
            self.browser.styleSheet()
            + "\nQTextBrowser { background: transparent; border: none; }"
        )
        self.browser.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        muted = "#9A9A9A" if isDarkTheme() else "#909090"
        code_bg = "#2D2D2D" if isDarkTheme() else "#F0F0F0"
        markdown = build_changelog_markdown(latest, current_only_version)
        self.browser.setHtml(
            changelog_to_html(markdown, muted=muted, code_bg=code_bg)
        )
        self.browser.document().setTextWidth(672)
        content_height = int(self.browser.document().size().height())
        self.browser.setFixedHeight(max(240, min(460, content_height + 12)))
        self.viewLayout.addWidget(self.browser)

        self.yesButton.hide()
        self.cancelButton.setText(strings.close)
        self.link_button = TransparentPushButton(
            FluentIcon.LINK,
            strings.app_changelog_open_browser,
            self,
        )
        self.link_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(VersionManager.RELEASES_URL))
        )
        self.buttonLayout.insertWidget(0, self.link_button)
