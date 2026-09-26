"""游戏补充抽取规则编辑与后台预览。"""
from __future__ import annotations

import copy
from pathlib import Path

from PyQt5.QtCore import QCoreApplication, QThread, Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget, QListWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QMessageBox, QScrollArea,
)
from qfluentwidgets import BodyLabel, CaptionLabel, LineEdit, PlainTextEdit, CheckBox, PushButton, PrimaryPushButton, ComboBox

from base.Base import Base
from base.EventManager import EventManager
from module.Extract.GameExtractionRules import RuleStore, RuleScan, RuleError, new_profile, new_rule, project_key, binding_key
from module.Localizer.Localizer import Localizer


def error_text(exc):
    if isinstance(exc, RuleError):
        return getattr(Localizer.get(), f"game_rules_error_{exc.code}", Localizer.get().game_rules_error_schema)
    return Localizer.get().game_rules_error_storage + '\n' + str(exc)


class RuleJob(QThread):
    """独立任务持有快照，窗口关闭时先取消再释放。"""
    def __init__(self, task):
        super().__init__(QCoreApplication.instance())
        self.task, self.result, self.error = task, None, None

    def run(self):
        try:
            self.result = self.task(self.isInterruptionRequested)
        except Exception as exc:
            self.error = exc


class GameExtractionRulesDialog(QDialog):
    def __init__(self, root: Path, language: str, parent=None, *, store=None, category="source", base=None, profile_id=None):
        super().__init__(parent)
        self.root, self.language = Path(root).resolve(), language
        self.store = store or RuleStore()
        self.category = category
        self.base = base or (self.root / 'game' / 'tl' / language if category == 'tl' else self.root / 'game')
        self.profile, self.scan = new_profile(category), None
        self.job, self.row, self.page = None, -1, 0
        self._loading, self._closing, self._dirty = True, False, False
        self.covered, self.declined = set(), set()
        self._project_invalid = False
        EventManager.get().subscribe(Base.Event.PROJECT_CHANGED, self._on_project_changed)
        self._subscribed = True
        self.finished.connect(self._unsubscribe)
        self.destroyed.connect(self._unsubscribe)
        l = Localizer.get()
        self.setWindowTitle(l.game_rules_title)
        self.resize(960, 800)
        layout = QVBoxLayout(self)
        self.content = QWidget()
        body = QVBoxLayout(self.content)
        body.setContentsMargins(0, 0, 0, 0)
        self.project_label = CaptionLabel(str(self.root))
        self.project_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(self.project_label)
        top = QHBoxLayout()
        self.profiles = ComboBox()
        self.profiles.currentIndexChanged.connect(self._choose_profile)
        top.addWidget(self.profiles, 1)
        for label, callback in [(l.game_rules_new_profile, self._new_profile), (l.game_rules_clone, self._clone), (l.game_rules_delete_profile, self._delete), (l.game_rules_unbind, self._unbind)]:
            button = PushButton(label)
            button.clicked.connect(callback)
            top.addWidget(button)
        body.addLayout(top)
        self.bindings = CaptionLabel('')
        self.bindings.setWordWrap(True)
        body.addWidget(self.bindings)
        meta = QFormLayout()
        self.name, self.note = LineEdit(), LineEdit()
        meta.addRow(l.game_rules_profile_name, self.name)
        meta.addRow(l.game_rules_note, self.note)
        body.addLayout(meta)
        self.tabs = QTabWidget()
        editor = QWidget()
        row_layout = QHBoxLayout(editor)
        sidebar = QVBoxLayout()
        self.rules = QListWidget()
        self.rules.setMaximumWidth(210)
        self.rules.currentRowChanged.connect(self._select_rule)
        sidebar.addWidget(self.rules)
        for label, callback in [(l.game_rules_add_rule, self._add_rule), (l.game_rules_remove_rule, self._remove_rule)]:
            button = PushButton(label)
            button.clicked.connect(callback)
            sidebar.addWidget(button)
        row_layout.addLayout(sidebar)
        self.form_widget = QWidget()
        form = QFormLayout(self.form_widget)
        self.enabled = CheckBox(l.game_rules_enabled)
        self.rule_name, self.scope, self.group, self.rule_note = LineEdit(), LineEdit(), LineEdit(), LineEdit()
        self.pattern, self.positive, self.negative = PlainTextEdit(), PlainTextEdit(), PlainTextEdit()
        for widget in (self.pattern, self.positive, self.negative):
            widget.setMaximumHeight(92)
        self.ignore_case = CheckBox(l.game_rules_ignore_case)
        for label, widget in [('', self.enabled), (l.game_rules_rule_name, self.rule_name), (l.game_rules_pattern, self.pattern), (l.game_rules_note, self.rule_note)]:
            form.addRow(label, widget)
        advanced_toggle = CheckBox(l.rpy_rules_advanced)
        form.addRow(advanced_toggle)
        advanced = QWidget()
        advanced_form = QFormLayout(advanced)
        for label, widget in [(l.game_rules_scope, self.scope), (l.game_rules_group, self.group), ('', self.ignore_case), (l.game_rules_positive, self.positive), (l.game_rules_negative, self.negative)]:
            advanced_form.addRow(label, widget)
        advanced.setVisible(False)
        advanced_toggle.toggled.connect(advanced.setVisible)
        form.addRow(advanced)
        hint = CaptionLabel(l.game_rules_literal_hint)
        hint.setWordWrap(True)
        form.addRow(hint)
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setWidget(self.form_widget)
        form_scroll.setFrameShape(QScrollArea.NoFrame)
        row_layout.addWidget(form_scroll, 1)
        self.tabs.addTab(editor, l.game_rules_edit_tab)
        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        self.stats = BodyLabel(l.game_rules_preview_needed)
        self.stats.setWordWrap(True)
        preview_layout.addWidget(self.stats)
        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels([l.game_rules_source, l.game_rules_text, l.game_rules_rule_name, l.game_rules_state])
        self.results.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.results.horizontalHeader().setStretchLastSection(True)
        self.results.setColumnWidth(0, 240)
        self.results.setColumnWidth(1, 340)
        preview_layout.addWidget(self.results)
        paging = QHBoxLayout()
        for label, delta in [(l.game_rules_previous, -1), (l.game_rules_next, 1)]:
            button = PushButton(label)
            button.clicked.connect(lambda _checked=False, d=delta: self._page(d))
            paging.addWidget(button)
        self.page_label = CaptionLabel('')
        paging.addWidget(self.page_label)
        preview_layout.addLayout(paging)
        self.tabs.addTab(preview, l.game_rules_preview_tab)
        body.addWidget(self.tabs, 1)
        actions = QHBoxLayout()
        self.preview_btn = PushButton(l.game_rules_preview)
        self.continue_btn = PushButton(l.game_rules_continue)
        self.draft_btn = PushButton(l.game_rules_save_draft)
        self.save_btn = PrimaryPushButton(l.game_rules_save_bind)
        for button, callback in [(self.preview_btn, self._preview), (self.continue_btn, self._continue), (self.draft_btn, self._save_draft), (self.save_btn, self._save)]:
            button.clicked.connect(callback)
            actions.addWidget(button)
        body.addLayout(actions)
        layout.addWidget(self.content, 1)
        self.status = CaptionLabel(l.game_rules_preview_needed)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        bottom = QHBoxLayout()
        self.cancel_btn, close_btn = PushButton(l.game_rules_cancel), PushButton(l.game_rules_close)
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        close_btn.clicked.connect(self.reject)
        bottom.addStretch(1)
        bottom.addWidget(self.cancel_btn)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)
        for widget in [self.name, self.note, self.rule_name, self.scope, self.group, self.rule_note, self.pattern, self.positive, self.negative]:
            widget.textChanged.connect(self._changed)
        self.enabled.stateChanged.connect(self._changed)
        self.ignore_case.stateChanged.connect(self._changed)
        self._loading = False
        self._reload(profile_id)

    def _unsubscribe(self, *_):
        if self._subscribed:
            EventManager.get().unsubscribe(Base.Event.PROJECT_CHANGED, self._on_project_changed)
            self._subscribed = False

    def _on_project_changed(self, event, data):
        root = data.get('project_root', '') if isinstance(data, dict) else ''
        if not root or project_key(Path(root)) != project_key(self.root):
            self._project_invalid = True
            self.scan = None
            self._cancel()
            self.content.setEnabled(False)
            self.status.setText(Localizer.get().game_rules_error_project_changed)

    def _changed(self, *_):
        if not self._loading:
            self.scan, self._dirty = None, True
            self.status.setText(Localizer.get().game_rules_preview_needed)
            self._buttons()

    def _buttons(self):
        self.save_btn.setEnabled(bool(self.scan and self.scan.completed and not self.scan.error))
        self.continue_btn.setEnabled(bool(self.scan and not self.scan.completed and not self.scan.error))

    def _flush(self):
        self.profile['name'], self.profile['note'] = self.name.text().strip(), self.note.text()
        if 0 <= self.row < len(self.profile['rules']):
            rule = self.profile['rules'][self.row]
            group = self.group.text().strip()
            rule.update(name=self.rule_name.text().strip(), enabled=self.enabled.isChecked(),
                        include_globs=[g.strip() for g in self.scope.text().split(';') if g.strip()],
                        pattern=self.pattern.toPlainText(), text_group=int(group) if group.isdecimal() else group,
                        note=self.rule_note.text(), flags=['IGNORECASE'] if self.ignore_case.isChecked() else [],
                        positive_samples=self.positive.toPlainText().splitlines(), negative_samples=self.negative.toPlainText().splitlines())
            self.rules.item(self.row).setText(rule['name'])

    def _select_rule(self, row):
        if self._loading:
            return
        self._flush()
        self.row = row
        self._loading = True
        self.form_widget.setEnabled(row >= 0)
        if row >= 0:
            rule = self.profile['rules'][row]
            self.enabled.setChecked(rule['enabled'])
            self.rule_name.setText(rule['name'])
            self.scope.setText('; '.join(rule['include_globs']))
            self.group.setText(str(rule['text_group']))
            self.rule_note.setText(rule['note'])
            self.pattern.setPlainText(rule['pattern'])
            self.positive.setPlainText('\n'.join(rule['positive_samples']))
            self.negative.setPlainText('\n'.join(rule['negative_samples']))
            self.ignore_case.setChecked(bool(rule['flags']))
        self._loading = False

    def _load_profile(self, profile):
        self._loading = True
        self.profile, self.scan, self.row = copy.deepcopy(profile), None, -1
        self.name.setText(profile['name'])
        self.note.setText(profile['note'])
        self.rules.clear()
        self.rules.addItems([r['name'] for r in profile['rules']])
        self._loading = False
        self.rules.setCurrentRow(0 if profile['rules'] else -1)
        self.form_widget.setEnabled(bool(profile['rules']))
        self._dirty = False
        self._buttons()

    def _reload(self, selected=None):
        try:
            self.data = self.store.load()
            self.data['profiles'] = [p for p in self.data['profiles'] if p.get('category', 'source') == self.category]
        except Exception as exc:
            self.content.setEnabled(False)
            self.status.setText(error_text(exc))
            return
        selected = selected or self.data['bindings'].get(binding_key(self.root, self.category))
        self._loading = True
        self.profiles.clear()
        self.profiles.addItem(Localizer.get().game_rules_new_profile, userData=None)
        for p in self.data['profiles']:
            self.profiles.addItem(p['name'], userData=p['id'])
        index = next((i + 1 for i, p in enumerate(self.data['profiles']) if p['id'] == selected), 0)
        self.profiles.setCurrentIndex(index)
        self._loading = False
        self._choose_profile(index)

    def _discard(self):
        return not self._dirty or QMessageBox.question(self, Localizer.get().game_rules_title, Localizer.get().game_rules_discard) == QMessageBox.Yes

    def _choose_profile(self, index):
        if self._loading:
            return
        if not self._discard():
            self._loading = True
            previous = next((i + 1 for i, p in enumerate(self.data['profiles']) if p['id'] == self.profile['id']), 0)
            self.profiles.setCurrentIndex(previous)
            self._loading = False
            return
        selected = self.profiles.itemData(index)
        profile = next((p for p in self.data['profiles'] if p['id'] == selected), None) or new_profile(self.category)
        if not profile['name']:
            profile['name'] = Localizer.get().game_rules_default_profile
        self._load_profile(profile)
        roots = [key.removesuffix('::tl') for key, value in self.data['bindings'].items() if value == profile['id']]
        self.bindings.setText(Localizer.get().game_rules_bindings.format(paths='; '.join(roots) or Localizer.get().game_rules_unbound))
        current = self.data['bindings'].get(binding_key(self.root, self.category)) == profile['id']
        self.status.setText(Localizer.get().game_rules_current_bound if current else Localizer.get().game_rules_preview_needed)

    def _new_profile(self):
        if self._discard():
            self._dirty = False
            if self.profiles.currentIndex() == 0:
                self._choose_profile(0)
            else:
                self.profiles.setCurrentIndex(0)

    def _clone(self):
        self._flush()
        profile = copy.deepcopy(self.profile)
        profile['id'] = new_profile()['id']
        profile['name'] += Localizer.get().game_rules_copy_suffix
        self._load_profile(profile)
        self._dirty = True
        self.bindings.setText(Localizer.get().game_rules_unbound)

    def _add_rule(self):
        self._flush()
        rule = new_rule()
        if self.category == 'tl':
            from frontend.RenpyToolbox.RpyExtractionPage import starter_profile
            rule = starter_profile('tl')['rules'][0]
        rule['name'] = Localizer.get().game_rules_default_rule.format(number=len(self.profile['rules']) + 1)
        rule['enabled'] = True
        self.profile['rules'].append(rule)
        self.rules.addItem(rule['name'])
        self.rules.setCurrentRow(len(self.profile['rules']) - 1)
        self._changed()

    def _remove_rule(self):
        if self.row < 0:
            return
        self._flush()
        profile = copy.deepcopy(self.profile)
        profile['rules'].pop(self.row)
        self._load_profile(profile)
        self._changed()

    def _run(self, task, done):
        if self.job is not None:
            return
        self.content.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status.setText(Localizer.get().game_rules_scanning)
        job = RuleJob(task)
        self.job = job
        def finished():
            self.job = None
            self.content.setEnabled(not self._project_invalid)
            self.cancel_btn.setEnabled(False)
            if self._project_invalid:
                self.status.setText(Localizer.get().game_rules_error_project_changed)
            elif job.error:
                self.status.setText(error_text(job.error))
            elif not self._closing:
                done(job.result)
            self._buttons()
            job.deleteLater()
            if self._closing:
                super(GameExtractionRulesDialog, self).reject()
        job.finished.connect(finished)
        job.start()

    def _preview(self):
        self._flush()
        profile = copy.deepcopy(self.profile)
        self.scan = None
        self.results.setRowCount(0)
        self.stats.setText(Localizer.get().game_rules_preview_needed)
        def task(cancel):
            scan = RuleScan(self.root, profile, cancel, base=self.base)
            scan.advance(cancel)
            return self._preview_payload(scan, cancel)
        self._run(task, self._preview_done)

    def _preview_payload(self, scan, cancel):
        if self.category == 'tl':
            return scan, set(), set()
        from module.Extract.UnifiedExtractor import UnifiedExtractor
        from module.Extract.ReplaceGenerator import load_declined_candidates
        extractor = UnifiedExtractor()
        extractor.set_cancel_callback(cancel)
        tl = self.root / 'game' / 'tl' / self.language
        covered = extractor._get_string_originals(tl)
        covered.update(extractor._collect_base_box_old_values(tl))
        covered.update(extractor._collect_source_registered_old_values(self.root, self.language))
        return scan, covered, load_declined_candidates(self.root, self.language)

    def _continue(self):
        if self.scan is None:
            return
        scan = self.scan
        def task(cancel):
            scan.advance(cancel)
            return self._preview_payload(scan, cancel)
        self._run(task, self._preview_done)

    def _preview_done(self, result):
        self.scan, self.covered, self.declined = result
        self.page = 0
        self.tabs.setCurrentIndex(1)
        self.status.setText(Localizer.get().game_rules_preview_complete if self.scan.completed else Localizer.get().game_rules_preview_partial)
        self._render_results()

    def _render_results(self):
        scan, l = self.scan, Localizer.get()
        if scan is None:
            return
        texts = {c.text for c in scan.candidates}
        self.stats.setText(l.game_rules_stats.format(files=scan.files_read, raw=scan.raw_matches, valid=len(texts), covered=len(texts & self.covered), filtered=scan.filtered, new=len(texts - self.covered - self.declined)))
        entries = [(c.path, c.line, c.text, c.rule_id, 'declined' if c.text in self.declined else 'covered' if c.text in self.covered else 'new') for c in scan.candidates]
        entries += [(path, line, '', '', reason) for path, line, reason in scan.diagnostics]
        pages = max(1, (len(entries) + 199) // 200)
        self.page = max(0, min(self.page, pages - 1))
        self.page_label.setText(f'{self.page + 1} / {pages}')
        self.results.setRowCount(0)
        names = {r['id']: r['name'] for r in self.profile['rules']}
        for path, line, text, rule_id, state in entries[self.page * 200:(self.page + 1) * 200]:
            row = self.results.rowCount()
            self.results.insertRow(row)
            for col, value in enumerate([f'{path}:{line}', text, names.get(rule_id, ''), getattr(l, f'game_rules_state_{state}', getattr(l, f'game_rules_error_{state}', state))]):
                self.results.setItem(row, col, QTableWidgetItem(value))

    def _page(self, delta):
        self.page += delta
        self._render_results()

    def _save(self):
        self._flush()
        profile, proof = copy.deepcopy(self.profile), self.scan
        def task(cancel):
            if cancel():
                raise RuleError('cancelled')
            self.store.save(profile, self.root, bind=True, proof=proof, cancel=cancel)
            mode, _ = self.store.selection(self.root, self.category)
            self.store.select(self.root, self.category, 'combined' if mode == 'builtin' else mode, profile['id'])
            return profile['id']
        self._run(task, self._saved)

    def _saved(self, profile_id):
        self._dirty = False
        self._reload(profile_id)
        self.status.setText(Localizer.get().game_rules_saved)

    def _save_draft(self):
        self._flush()
        profile = copy.deepcopy(self.profile)
        for rule in profile['rules']:
            rule['enabled'] = False
        def task(cancel):
            if cancel():
                raise RuleError('cancelled')
            self.store.save(profile, self.root, bind=False)
            return profile['id']
        def done(profile_id):
            self._saved(profile_id)
            self.status.setText(Localizer.get().game_rules_draft_saved)
        self._run(task, done)

    def _unbind(self):
        if self._discard():
            def done(result):
                self._saved(self.profile['id'])
                self.status.setText(Localizer.get().game_rules_unbound_done)
            self._run(lambda cancel: self.store.unbind(self.root, self.category), done)

    def _delete(self):
        if QMessageBox.question(self, Localizer.get().game_rules_title, Localizer.get().game_rules_delete_confirm) == QMessageBox.Yes:
            def done(result):
                self._saved(None)
                self.status.setText(Localizer.get().game_rules_deleted)
            self._run(lambda cancel: self.store.delete(self.profile['id']), done)

    def _cancel(self):
        if self.job:
            self.job.requestInterruption()

    def reject(self):
        if self.job:
            self._closing = True
            self._cancel()
        elif self._discard():
            super().reject()

    def closeEvent(self, event):
        event.ignore()
        self.reject()


def open_game_rules(root, language, parent):
    from frontend.RenpyToolbox.RpyExtractionPage import open_rpy_settings
    open_rpy_settings(root, language, parent, 'source')
