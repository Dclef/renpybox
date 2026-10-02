"""独立的 RPY 抽取设置及翻译页面共用入口。"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QDialog, QFileDialog, QMessageBox, QFormLayout
from qfluentwidgets import BodyLabel, CaptionLabel, TitleLabel, ComboBox, PushButton, PrimaryPushButton, LineEdit, CheckBox

from module.Config import Config
from module.Extract.GameExtractionRules import RuleStore, RuleError, new_profile, new_rule
from module.Extract.RpyExtractionSettings import context_for_path
from module.Localizer.Localizer import Localizer
from widget.ThemeHelper import mark_app_dialog, mark_app_page


def starter_profile(category):
    """提供可编辑的常见语法模板，内置语法解析器本身不转换为正则。"""
    l = Localizer.get()
    profile = new_profile(category)
    profile['name'] = l.rpy_rules_template
    literal = r'(?P<text>"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27)'
    examples = (
        [(l.rpy_rules_dialogue, r'^\s*(?:[a-zA-Z_]\w*\s+)?' + literal + r'\s*$', 'e "Hello."'),
         (l.rpy_rules_menu, r'^\s*' + literal + r'\s*:\s*$', '"Continue":'),
         (l.rpy_rules_ui, r'^\s*(?:text|textbutton)\s+' + literal + r'\s*$', 'text "Hello."')]
        if category == 'source' else
        [(l.rpy_rules_strings, r'^\s*old\s+' + literal + r'\s*$', 'old "Hello."'),
         (l.rpy_rules_dialogue, r'^\s*(?!(?:old|new)\b)(?:[a-zA-Z_]\w*\s+)?' + literal + r'\s*$', 'e "Hello."')]
    )
    for name, pattern, example in examples:
        rule = new_rule()
        rule.update(name=name, enabled=True, pattern=pattern, positive_samples=[example], negative_samples=['jump next_label'])
        profile['rules'].append(rule)
    return profile


class RpySettingsWidget(QWidget):
    """按当前路径读取方案，修改后显式应用，避免路径切换时误保存。"""
    def __init__(self, path, language, category, parent=None):
        super().__init__(parent)
        self.path, self.language, self.category = path, language, category
        self.store = RuleStore()
        self.root = self.base = None
        # 已生效的选择。摘要要在它与当前下拉值不一致时显示"未保存"，
        # 否则用户改完只看到一行没变的"当前已生效：…"，
        # 会以为改动没生效、或者反过来以为已经生效。
        self._applied_mode = None
        self._applied_profile = None
        self._applied_name = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        l = Localizer.get()
        # 分类名和"哪些流程用这份规则"由外层页面显示，这里不重复标题。
        layout.addWidget(CaptionLabel(l.rpy_rules_beginner_steps))

        self.mode = ComboBox()
        self.mode.addItem(l.rpy_rules_builtin_simple, userData='builtin')
        self.mode.addItem(l.rpy_rules_combined_simple, userData='combined')
        self.mode.addItem(l.rpy_rules_custom_simple, userData='custom')
        mode_form = QFormLayout()
        mode_form.addRow(l.rpy_rules_method, self.mode)
        layout.addLayout(mode_form)
        self.mode_hint = CaptionLabel('')
        self.mode_hint.setWordWrap(True)
        layout.addWidget(self.mode_hint)

        self.profile_label = BodyLabel(l.rpy_rules_profile)
        self.profile = ComboBox()
        profile_row = QHBoxLayout()
        profile_row.addWidget(self.profile_label)
        profile_row.addWidget(self.profile, 1)
        layout.addLayout(profile_row)

        self.advanced_toggle = CheckBox(l.rpy_rules_advanced_toggle)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        layout.addWidget(self.advanced_toggle)
        self.advanced_actions = QWidget()
        advanced_row = QHBoxLayout(self.advanced_actions)
        advanced_row.setContentsMargins(0, 0, 0, 0)
        self.edit_button = PushButton(l.rpy_rules_edit)
        self.copy_button = PushButton(l.rpy_rules_copy_builtin)
        self.apply_button = PrimaryPushButton(l.rpy_rules_apply)
        self.edit_button.clicked.connect(self.edit)
        self.copy_button.clicked.connect(self.copy_builtin)
        self.apply_button.clicked.connect(self.apply)
        advanced_row.addWidget(self.edit_button)
        advanced_row.addWidget(self.copy_button)
        advanced_row.addStretch(1)
        advanced_row.addWidget(self.apply_button)
        self.advanced_actions.setVisible(False)
        layout.addWidget(self.advanced_actions)
        self.apply_button_simple = PrimaryPushButton(l.rpy_rules_apply)
        self.apply_button_simple.clicked.connect(self.apply)
        layout.addWidget(self.apply_button_simple)
        self.summary = CaptionLabel('')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.mode.currentIndexChanged.connect(self._sync_beginner_ui)
        self.mode.currentIndexChanged.connect(self._refresh_summary)
        self.profile.currentIndexChanged.connect(self._refresh_summary)
        self.reload()

    def _selection_label(self, mode, name):
        l = Localizer.get()
        return l.rpy_rules_current.format(mode=getattr(l, 'rpy_rules_' + mode), name=name)

    def _pending_label(self):
        l = Localizer.get()
        return l.rpy_rules_pending.format(
            mode=getattr(l, 'rpy_rules_' + (self.mode.currentData() or 'builtin')),
            name=self.profile.currentText() or l.rpy_rules_no_profile,
        )

    def _refresh_summary(self, *_):
        """下拉一变就把摘要切成"未保存"，让用户看见改动还没落盘。"""
        if self.root is None:
            return
        applied = (self._applied_mode, self._applied_profile)
        if (self.mode.currentData(), self.profile.currentData()) == applied:
            name = self._applied_name
            self.summary.setText(self._selection_label(self._applied_mode, name))
        else:
            self.summary.setText(self._pending_label())

    def reload(self):
        from frontend.RenpyToolbox.GameExtractionRulesDialog import error_text
        l = Localizer.get()
        try:
            if not str(self.path() or '').strip():
                raise RuleError('project')
            self.root, self.base = context_for_path(self.path(), self.category, self.language())
            mode, selected = self.store.selection(self.root, self.category)
            # 先记下生效值再设下拉：设置下拉会触发 _refresh_summary，
            # 那时它需要和"当前下拉"比较，而不是和一个空基线比较。
            self._applied_mode = mode
            self._applied_profile = selected['id'] if selected else None
            self._applied_name = selected['name'] if selected else l.rpy_rules_no_profile
            self.mode.setCurrentIndex(self.mode.findData(mode))
            self.profile.clear()
            self.profile.addItem(l.rpy_rules_no_profile, userData=None)
            for p in self.store.load()['profiles']:
                if p.get('category', 'source') == self.category:
                    self.profile.addItem(p['name'], userData=p['id'])
            if selected:
                self.profile.setCurrentIndex(self.profile.findData(selected['id']))
            self.summary.setText(self._selection_label(mode, self._applied_name))
            self._sync_beginner_ui()
        except Exception as exc:
            self.root = self.base = None
            self._applied_mode = None
            self._applied_profile = None
            self._applied_name = None
            self.summary.setText(error_text(exc))

    def _toggle_advanced(self, checked):
        # 选了"只用我的规则/默认＋我的规则"时，方案下拉和管理按钮都住在高级区里。
        # 这时候把它收起来等于把唯一能改规则的入口藏掉，所以拒绝折叠并把勾选弹回去。
        if not checked and (self.mode.currentData() or 'builtin') != 'builtin':
            self.advanced_toggle.setChecked(True)
            return
        self.advanced_actions.setVisible(checked)
        self.apply_button_simple.setVisible(not checked)

    def _sync_beginner_ui(self, *_):
        mode = self.mode.currentData() or 'builtin'
        l = Localizer.get()
        hints = {
            'builtin': l.rpy_rules_builtin_help,
            'combined': l.rpy_rules_combined_help,
            'custom': l.rpy_rules_custom_help,
        }
        self.mode_hint.setText(hints[mode])
        needs_profile = mode != 'builtin'
        self.profile_label.setVisible(needs_profile)
        self.profile.setVisible(needs_profile)
        if needs_profile:
            self.advanced_toggle.setChecked(True)
        elif self.advanced_toggle.isChecked():
            self.advanced_toggle.setChecked(False)

    def showEvent(self, event):
        super().showEvent(event)
        self.reload()

    def apply(self):
        from frontend.RenpyToolbox.GameExtractionRulesDialog import error_text
        try:
            root, _ = context_for_path(self.path(), self.category, self.language())
            if self.root is None or root != self.root:
                raise RuleError('project_changed')
            mode, profile_id = self.mode.currentData(), self.profile.currentData()
            if mode != 'builtin' and not profile_id:
                raise RuleError('binding')
            if mode == 'custom':
                p = next(p for p in self.store.load()['profiles'] if p['id'] == profile_id)
                if not any(r['enabled'] for r in p['rules']):
                    raise RuleError('empty_custom')
            self.store.select(root, self.category, mode, profile_id)
            self.reload()
        except Exception as exc:
            QMessageBox.warning(self, Localizer.get().rpy_rules_title, error_text(exc))

    def edit(self, _checked=False, *, template=False):
        from frontend.RenpyToolbox.GameExtractionRulesDialog import GameExtractionRulesDialog
        if self.root is None:
            QMessageBox.warning(self, Localizer.get().rpy_rules_title, Localizer.get().game_rules_error_project)
            return
        dialog = GameExtractionRulesDialog(self.root, self.language(), self, store=self.store,
                                           category=self.category, base=self.base, profile_id=self.profile.currentData())
        if template:
            dialog._load_profile(starter_profile(self.category))
            dialog._dirty = True
        dialog.exec()
        self.reload()

    def copy_builtin(self):
        self.edit(template=True)


class RpyExtractionPage(QWidget):
    # settings 容器插在分类下拉之后、语言输入之前。写成常量而不是行号 5：
    # 上面每加一个控件，这个魔数就会静默把设置区插到错误位置。
    _SETTINGS_INDEX = 4

    def __init__(self, object_name='rpy-extraction-settings', parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        mark_app_page(self)
        l = Localizer.get()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(TitleLabel(l.rpy_rules_title))
        row = QHBoxLayout()
        self.path = LineEdit()
        self.path.setPlaceholderText(l.rpy_rules_path)
        browse = PushButton(l.browse)
        browse.clicked.connect(self.browse)
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        self.category = ComboBox()
        self.category.addItem(l.rpy_rules_source, userData='source')
        self.category.addItem(l.rpy_rules_tl, userData='tl')
        layout.addWidget(self.category)
        # 分类下拉和这句"哪些流程用这份规则"是一对，切换分类时一起更新，
        # 免得下拉停在"TL RPY"、说明还写着源码流程用哪些规则。
        self.category_scope = CaptionLabel('')
        self.category_scope.setWordWrap(True)
        layout.addWidget(self.category_scope)
        self.category.currentIndexChanged.connect(self._sync_category_scope)
        self._sync_category_scope()
        lang = QHBoxLayout()
        lang.addWidget(BodyLabel(l.rpy_rules_language))
        self.language = LineEdit()
        self.language.setText('chinese')
        lang.addWidget(self.language)
        layout.addLayout(lang)
        self.hint = CaptionLabel(l.rpy_rules_builtin_description)
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        config = Config().load()
        self.path.setText(str(getattr(config, 'renpy_game_folder', '') or ''))
        self.settings = None
        self.category.currentIndexChanged.connect(self.refresh)
        self.path.editingFinished.connect(self.refresh)
        self.language.editingFinished.connect(self.refresh)
        self.refresh()
        layout.addStretch(1)

    def _sync_category_scope(self, *_):
        l = Localizer.get()
        self.category_scope.setText(
            l.rpy_rules_source_scope if self.category.currentData() == 'source' else l.rpy_rules_tl_scope
        )

    def refresh(self):
        if self.settings is not None:
            self.layout().removeWidget(self.settings)
            self.settings.deleteLater()
        self.settings = RpySettingsWidget(self.path.text, self.language.text, self.category.currentData(), self)
        self.layout().insertWidget(self._SETTINGS_INDEX, self.settings)

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, Localizer.get().rpy_rules_path, self.path.text())
        if path:
            self.path.setText(path)
            self.refresh()


def open_rpy_settings(path, language, parent, category='source'):
    dialog = QDialog(parent)
    dialog.setWindowTitle(Localizer.get().rpy_rules_title)
    dialog.resize(760, 440)
    mark_app_dialog(dialog)
    layout = QVBoxLayout(dialog)
    page = RpyExtractionPage(parent=dialog)
    page.path.setText(str(path or ''))
    page.language.setText(language or 'chinese')
    page.category.setCurrentIndex(page.category.findData(category))
    page.refresh()
    layout.addWidget(page)
    close = PrimaryPushButton(Localizer.get().game_rules_close)
    close.clicked.connect(dialog.accept)
    layout.addWidget(close)
    dialog.exec()


class RpySettingsEntry(QWidget):
    """翻译入口只显示已生效方案与设置按钮。"""
    def __init__(self, path, language, category, parent=None):
        super().__init__(parent)
        self.path, self.language, self.category = path, language, category
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        self.summary = CaptionLabel('')
        self.summary.setWordWrap(True)
        row.addWidget(self.summary, 1)
        self.button = PushButton(Localizer.get().rpy_rules_title)
        self.button.clicked.connect(self.open)
        row.addWidget(self.button)
        self.refresh()

    def refresh(self, *_):
        l = Localizer.get()
        try:
            if not str(self.path() or '').strip():
                self.summary.setText(l.rpy_rules_path)
                return
            root, _ = context_for_path(self.path(), self.category, self.language())
            mode, profile = RuleStore().selection(root, self.category)
            self.summary.setText(l.rpy_rules_current.format(mode=getattr(l, 'rpy_rules_' + mode), name=profile['name'] if profile else l.rpy_rules_no_profile))
        except Exception:
            self.summary.setText(l.game_rules_error_storage)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def open(self):
        open_rpy_settings(self.path(), self.language(), self, self.category)
        self.refresh()
