from __future__ import annotations

from datetime import datetime
from typing import Any

from PyQt5.QtWidgets import QFrame
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import CaptionLabel
from qfluentwidgets import FluentIcon
from qfluentwidgets import MessageBoxBase
from qfluentwidgets import SubtitleLabel
from qfluentwidgets import TextBrowser

from base.VersionManager import VersionManager
from module.Localizer.Localizer import Localizer


def _asset_from_latest(latest: dict[str, Any]) -> dict[str, Any]:
    asset = latest.get("asset")
    return asset if isinstance(asset, dict) else latest


def format_file_size(size: object) -> str:
    try:
        value = max(0, int(size))
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        return Localizer.get().app_update_size_unknown
    return f"{value / (1024 * 1024):.1f} MB"


def format_published_at(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return Localizer.get().app_update_date_unknown
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return raw


class UpdateDetailsDialog(MessageBoxBase):
    """Show release notes before the user explicitly starts a download."""

    def __init__(self, latest: dict[str, Any], parent: QWidget) -> None:
        super().__init__(parent)
        self.latest = dict(latest or {})
        self._init_ui()

    def _init_ui(self) -> None:
        strings = Localizer.get()
        version = VersionManager.display_version(self.latest.get("tag_name", ""))
        asset = _asset_from_latest(self.latest)

        self.widget.setMinimumWidth(720)
        self.viewLayout.setContentsMargins(24, 24, 24, 24)
        self.viewLayout.setSpacing(16)
        self.viewLayout.addWidget(SubtitleLabel(
            strings.app_update_details_title.replace("{VERSION}", version),
            self.widget,
        ))

        notes = TextBrowser(self.widget)
        notes.setReadOnly(True)
        notes.setOpenExternalLinks(True)
        notes.setMinimumHeight(240)
        notes.setMaximumHeight(400)
        # 弹窗卡片本身已是容器，去掉内层边框避免盒中盒。
        notes.setFrameShape(QFrame.NoFrame)
        notes.setStyleSheet(
            notes.styleSheet()
            + "\nQTextBrowser { background: transparent; border: none; }"
        )
        notes.setMarkdown(
            str(self.latest.get("body", "")).strip()
            or strings.app_update_notes_empty
        )
        self.viewLayout.addWidget(notes)

        size = asset.get("size", self.latest.get("total_size", 0))
        metadata = strings.app_update_release_metadata
        metadata = metadata.replace("{SIZE}", format_file_size(size))
        metadata = metadata.replace(
            "{DATE}",
            format_published_at(self.latest.get("published_at")),
        )
        self.viewLayout.addWidget(CaptionLabel(metadata, self.widget))

        self.yesButton.setText(strings.app_update_download)
        self.cancelButton.setText(strings.later)
        self.yesButton.setIcon(FluentIcon.CLOUD_DOWNLOAD)

