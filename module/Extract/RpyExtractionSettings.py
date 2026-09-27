"""源码与 TL 共用抽取方案；结构解析和写回定位始终保留。"""
import time
from pathlib import Path

from module.Extract.GameExtractionRules import (
    RuleError, RuleScan, _check_budget, _matches_scope, compile_rule,
)
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Renpy.renpy_tl_io import RenpyTlItemExtractor
from module.Renpy.renpy_tl_core import TlBlockKind, TlSlot, TlSlotRole


def context_for_path(path, category, language='chinese'):
    path = Path(path).resolve()
    cursor = path.parent if path.is_file() else path
    if category == 'source':
        for parent in (cursor, *cursor.parents):
            if parent.name.casefold() == 'game':
                return parent.parent, parent
    explicit_tl = category == 'tl' and cursor.name.casefold() != 'tl' and any(p.name.casefold() == 'tl' for p in cursor.parents)
    paths = RenpyProjectPaths.from_path(path, '' if explicit_tl else language)
    root = paths.project_root if paths else cursor
    base = paths.tl_language_dir if category == 'tl' else paths.game_dir
    if not base.is_dir():
        base = cursor
    return root, base


def selection_for_path(path, category, store=None):
    from module.Extract.GameExtractionRules import RuleStore
    root, _ = context_for_path(path, category)
    mode, profile = (store or RuleStore()).selection(root, category)
    if mode != 'builtin' and not profile:
        raise RuleError('binding')
    if mode == 'custom' and not any(r['enabled'] for r in profile['rules']):
        raise RuleError('empty_custom')
    return root, mode, profile


def scan_source(root, profile, cancel=None, *, base=None, paths=None):
    scan = RuleScan(root, profile, cancel, base=base, paths=paths)
    deadline = time.monotonic() + 300
    while not scan.completed:
        _check_budget(cancel, deadline)
        scan.advance(cancel)
    return scan


class ProfileTlExtractor(RenpyTlItemExtractor):
    """正则选择 TL 原文槽位，继续使用原有 old/new 配对及写回元数据。"""
    def __init__(self, mode='builtin', profile=None, *, cancel=None, deadline=None):
        super().__init__()
        self.mode = mode
        self.cancel = cancel
        self.deadline = deadline if deadline is not None else time.monotonic() + 300
        self.rules = [(r, compile_rule(r)) for r in (profile or {}).get('rules', []) if r['enabled']]
        self.relative = ''
        self._active_rules = []
        self.custom_selected = False

    def extract(self, doc, rel_path, *, scope_path=None):
        self.relative = scope_path if scope_path is not None else rel_path
        # 作用域对同一个文件内的所有语句都相同，只判断一次，避免逐语句重复匹配 glob。
        self._active_rules = [
            (rule, compiled)
            for rule, compiled in self.rules
            if any(_matches_scope(self.relative, glob) for glob in rule['include_globs'])
        ]
        return super().extract(doc, rel_path)

    def _build_cache_item(self, block, template_stmt, target_stmt, rel_path, statement_ordinal=None):
        item = super()._build_cache_item(block, template_stmt, target_stmt, rel_path, statement_ordinal)
        if item is not None and self.custom_selected:
            extra = item.get_extra_field()
            if any(s['lit_index'] >= len(target_stmt.literals) for s in extra['renpy']['slots']):
                raise RuleError('ambiguous')
            extra['renpy']['custom_selection'] = True
            item.set_extra_field(extra)
        return item

    def _select_slots(self, block, stmt):
        self.custom_selected = False
        builtin = super()._select_slots(block, stmt) if self.mode != 'custom' else []
        if self.mode == 'builtin':
            return builtin
        chosen = set()
        for rule, compiled in self._active_rules:
            _check_budget(self.cancel, self.deadline)
            try:
                for match in compiled.finditer(stmt.code, timeout=0.05):
                    span = match.span(rule['text_group'])
                    for index, literal in enumerate(stmt.literals):
                        if span == (literal.start_col, literal.end_col) and literal.value.strip():
                            chosen.add(index)
            except TimeoutError as exc:
                raise RuleError('timeout', rule['id']) from exc
        if not chosen:
            return builtin
        # 一条 TL 语句只有一个正文槽位；歧义必须由用户收窄规则。
        if len(chosen) != 1:
            raise RuleError('ambiguous')
        self.custom_selected = True
        index = chosen.pop()
        role = TlSlotRole.STRING if block.kind == TlBlockKind.STRINGS else TlSlotRole.DIALOGUE
        names = [s for s in builtin if s.role == TlSlotRole.NAME and s.lit_index != index]
        return names + [TlSlot(role=role, lit_index=index)]

class RecordedTlExtractor(RenpyTlItemExtractor):
    """写回时沿用缓存中的槽位，不受用户后来切换方案影响。"""
    def __init__(self, items):
        super().__init__()
        self.selected = {}
        self.restrict = any(item.get_extra_field().get('renpy', {}).get('custom_selection') for item in items)
        for item in items:
            meta = item.get_extra_field().get('renpy', {})
            if self.restrict and meta.get('slots'):
                block = meta['block']
                key = (block['lang'], block['label'], meta['digest']['template_raw_sha1'])
                self.selected[key] = meta['slots']

    def _select_slots(self, block, stmt):
        from module.Renpy.renpy_tl_core import sha1_hex
        slots = self.selected.get((block.lang, block.label, sha1_hex(stmt.raw_line)))
        if slots is not None:
            return [TlSlot(role=TlSlotRole(s['role']), lit_index=s['lit_index']) for s in slots]
        return [] if self.restrict else super()._select_slots(block, stmt)
