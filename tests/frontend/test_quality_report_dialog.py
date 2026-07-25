from PyQt5.QtCore import Qt

from frontend.Proofreading.QualityReportDialog import QualityReportDialog


class _CheckBoxStub:
    def __init__(self, checked: bool) -> None:
        self.checked = checked

    def isChecked(self) -> bool:
        return self.checked

    def setChecked(self, checked: bool) -> None:
        self.checked = checked


class _ButtonStub:
    def __init__(self) -> None:
        self.enabled: bool | None = None

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled


class _ItemStub:
    def __init__(self, item_index: int) -> None:
        self.item_index = item_index
        self.requested_roles: list[int] = []

    def data(self, role: int) -> int:
        self.requested_roles.append(role)
        return self.item_index


class _DialogStub:
    def __init__(self, item_checkboxes: dict[int, _CheckBoxStub]) -> None:
        self.item_checkboxes = item_checkboxes
        self.yesButton = _ButtonStub()

    def get_selected_item_indices(self) -> tuple[int, ...]:
        return QualityReportDialog.get_selected_item_indices(self)


def test_format_error_counts_is_sorted_and_handles_empty_counts() -> None:
    assert QualityReportDialog._format_error_counts({}) == "-"
    assert QualityReportDialog._format_error_counts({
        "TIMEOUT": 2,
        "FAIL_LINE_COUNT": 3,
    }) == "FAIL_LINE_COUNT: 3, TIMEOUT: 2"


def test_selected_item_indices_only_returns_checked_items_in_index_order() -> None:
    dialog = _DialogStub({
        8: _CheckBoxStub(True),
        2: _CheckBoxStub(True),
        5: _CheckBoxStub(False),
    })

    assert dialog.get_selected_item_indices() == (2, 8)


def test_item_click_toggles_selection_and_updates_confirmation_button() -> None:
    checkbox = _CheckBoxStub(True)
    dialog = _DialogStub({4: checkbox})
    item = _ItemStub(4)

    QualityReportDialog._on_item_clicked(dialog, item)

    assert checkbox.isChecked() is False
    assert dialog.yesButton.enabled is False
    assert item.requested_roles == [Qt.UserRole]

    QualityReportDialog._on_item_clicked(dialog, item)

    assert checkbox.isChecked() is True
    assert dialog.yesButton.enabled is True
