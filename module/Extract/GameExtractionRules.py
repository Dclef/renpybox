"""按游戏保存的补充提取规则；扫描只读，预览与正式提取共用执行器。"""
from __future__ import annotations

import ast
import copy
import fnmatch
from functools import lru_cache
import hashlib
import io
import json
import os
import time
import tokenize
import uuid
from dataclasses import dataclass
from pathlib import Path

import regex

from base.AppPaths import get_app_paths
from base.LogManager import LogManager
from module.File.AtomicWrite import atomic_write_text

MATCH_TIMEOUT = 0.05
MAX_LINE = 32768
MAX_LITERAL = 16384
MAX_RESULTS = 100000


class RuleError(ValueError):
    """用稳定错误码供界面本地化，不把规则当作代码执行。"""
    def __init__(self, code: str, detail: str = ""):
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


def project_key(root: Path) -> str:
    return os.path.normcase(str(Path(root).resolve())).replace("\\", "/")


def binding_key(root, category="source"):
    return project_key(root) + ("::tl" if category == "tl" else "")


def signature(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def new_profile(category="source") -> dict:
    return {"id": uuid.uuid4().hex, "name": "", "note": "", "rules": [], "category": category}


def new_rule() -> dict:
    return {
        "id": uuid.uuid4().hex, "name": "", "enabled": False,
        "include_globs": ["*.rpy", "**/*.rpy"],
        "pattern": r'\bcall\s+reply_message\(\s*(?P<text>"(?:\\.|[^"\\])*")\s*\)',
        "flags": [], "text_group": "text", "note": "",
        "positive_samples": ['call reply_message("Try again.")'],
        "negative_samples": ['call reply_message(player_name)'],
    }


def _text(value, limit=MAX_LINE, *, empty=True):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise RuleError("schema")


def validate_profile(profile: dict) -> None:
    if not isinstance(profile, dict):
        raise RuleError("schema")
    for key in ("id", "name", "note"):
        _text(profile.get(key), 2000, empty=key == "note")
    if profile.get("category", "source") not in {"source", "tl"}:
        raise RuleError("schema")
    rules = profile.get("rules")
    if not isinstance(rules, list) or len(rules) > 100:
        raise RuleError("schema")
    ids = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise RuleError("schema")
        for key in ("id", "name", "note", "pattern"):
            _text(rule.get(key), 4096, empty=key in {"note", "pattern"})
        if rule['id'] in ids or type(rule.get('enabled')) is not bool:
            raise RuleError("schema")
        ids.add(rule['id'])
        group = rule.get("text_group")
        if not ((type(group) is int and group > 0) or (isinstance(group, str) and group.isidentifier())):
            raise RuleError("group")
        globs = rule.get("include_globs")
        if not isinstance(globs, list) or not 1 <= len(globs) <= 32:
            raise RuleError("scope")
        for glob in globs:
            _text(glob, 256, empty=False)
            if (glob.startswith('/') or any(ch in glob for ch in '\\:\x00')
                    or any(part in ('', '.', '..') for part in glob.split('/'))
                    or any('**' in part and part != '**' for part in glob.split('/'))):
                raise RuleError("scope", glob)
        flags = rule.get("flags")
        if not isinstance(flags, list) or any(flag != "IGNORECASE" for flag in flags):
            raise RuleError("schema")
        for key in ("positive_samples", "negative_samples"):
            samples = rule.get(key)
            if not isinstance(samples, list) or len(samples) > 40:
                raise RuleError("samples")
            for sample in samples:
                _text(sample, MAX_LINE, empty=False)
                if '\n' in sample or '\r' in sample:
                    raise RuleError("samples")


class RuleStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else get_app_paths().app("storage", "game_extraction_profiles.json")

    def load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": 1, "profiles": [], "bindings": {}}
        try:
            if self.path.stat().st_size > 8 * 1024 * 1024:
                raise RuleError("schema")
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema_version") != 1:
                raise RuleError("schema")
            profiles, bindings = data.get("profiles"), data.get("bindings")
            if not isinstance(profiles, list) or len(profiles) > 200 or not isinstance(bindings, dict):
                raise RuleError("schema")
            ids = set()
            for profile in profiles:
                validate_profile(profile)
                if profile['id'] in ids:
                    raise RuleError("schema")
                ids.add(profile['id'])
            if any(not isinstance(key, str) or value not in ids for key, value in bindings.items()):
                raise RuleError("binding")
            if not isinstance(data.get('modes', {}), dict):
                raise RuleError('schema')
            for key, mode in data.get('modes', {}).items():
                if not isinstance(key, str) or mode not in {'builtin', 'combined', 'custom'}:
                    raise RuleError('schema')
            return data
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            if isinstance(exc, RuleError):
                raise
            raise RuleError("storage", str(exc)) from exc

    def bound_profile(self, root: Path, category="source") -> dict | None:
        data = self.load()
        bound = data['bindings'].get(binding_key(root, category))
        return next((p for p in data['profiles'] if p['id'] == bound), None)

    def _write(self, data):
        text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        if len(data['profiles']) > 200 or len(text.encode('utf-8')) > 8 * 1024 * 1024:
            raise RuleError("schema")
        try:
            atomic_write_text(self.path, text)
        except OSError as exc:
            raise RuleError("storage", str(exc)) from exc
        LogManager.get().info(f"保存游戏规则: path={self.path}, schema_version=1")

    def save(self, profile: dict, root: Path, *, bind: bool, proof=None, cancel=None):
        validate_profile(profile)
        if any(r['enabled'] for r in profile['rules']):
            if proof is None or not proof.completed or proof.error or proof.profile != profile or proof.root != Path(root).resolve():
                raise RuleError("preview_required")
            proof.verify_sources(cancel, time.monotonic() + 20)
        data = self.load()
        data['profiles'] = [p for p in data['profiles'] if p['id'] != profile['id']] + [copy.deepcopy(profile)]
        if bind:
            data['bindings'][binding_key(root, profile.get('category', 'source'))] = profile['id']
        self._write(data)

    def unbind(self, root: Path, category="source"):
        data = self.load()
        key = binding_key(root, category)
        data['bindings'].pop(key, None)
        data.setdefault('modes', {})[key] = 'builtin'
        self._write(data)

    def selection(self, root, category="source"):
        data = self.load()
        key = binding_key(root, category)
        profile = next((p for p in data['profiles'] if p['id'] == data['bindings'].get(key)), None)
        if profile and profile.get('category', 'source') != category:
            raise RuleError('binding')
        # 老版本的项目绑定继续作为补充规则使用。
        return data.get('modes', {}).get(key, 'combined' if profile else 'builtin'), profile

    def select(self, root, category, mode, profile_id=None):
        if category not in {'source', 'tl'} or mode not in {'builtin', 'combined', 'custom'}:
            raise RuleError('schema')
        data = self.load()
        if profile_id is not None:
            profile = next((p for p in data['profiles'] if p['id'] == profile_id), None)
            if profile is None or profile.get('category', 'source') != category:
                raise RuleError('binding')
        key = binding_key(root, category)
        if profile_id:
            data['bindings'][key] = profile_id
        else:
            data['bindings'].pop(key, None)
        data.setdefault('modes', {})[key] = mode
        self._write(data)

    def delete(self, profile_id: str):
        data = self.load()
        if profile_id in data['bindings'].values():
            raise RuleError("bound")
        data['profiles'] = [p for p in data['profiles'] if p['id'] != profile_id]
        self._write(data)


def _matches_scope(relative: str, glob: str) -> bool:
    # 每段独立匹配，** 才能跨目录；根目录的 *.rpy 不隐式匹配子目录。
    parts, patterns = relative.split('/'), glob.split('/')
    @lru_cache(maxsize=None)
    def match(i, j):
        if j == len(patterns):
            return i == len(parts)
        if patterns[j] == '**':
            return match(i, j + 1) or (i < len(parts) and match(i + 1, j))
        return i < len(parts) and fnmatch.fnmatchcase(parts[i], patterns[j]) and match(i + 1, j + 1)
    return match(0, 0)


def _excluded(name: str) -> bool:
    name = name.casefold()
    return (name.startswith(('.', '_temp_extract_', '_tl_backup', 'tl_backup', 'replace_text_auto', 'miss_ready_replace', 'zz_renpybox_'))
            or name in {'tl', 'miss', 'cache', 'saves', 'base_box', '_filtered_suspicious', 'renpybox_translation'}
            or 'backup' in name or name.endswith(('.bak', '.old')))


def source_manifest(root: Path, rules: list, cancel=None, deadline=None, *, base=None, paths=None) -> list[tuple]:
    game = Path(base).resolve() if base is not None else (root / 'game').resolve()
    if not game.is_dir():
        raise RuleError("project")
    if not rules:
        return []
    result, seen = [], set()
    def error(exc):
        raise RuleError("read", str(exc))
    for directory, dirs, files in os.walk(game, followlinks=False, onerror=error):
        _check_budget(cancel, deadline)
        current = Path(directory).resolve()
        if not current.is_relative_to(game) or current in seen:
            dirs[:] = []
            continue
        seen.add(current)
        dirs[:] = sorted(d for d in dirs if not _excluded(d) and (Path(directory) / d).resolve().is_relative_to(game))
        for name in sorted(files):
            _check_budget(cancel, deadline)
            if not name.casefold().endswith('.rpy') or _excluded(name):
                continue
            path = Path(directory) / name
            if paths is not None and path.resolve() not in paths:
                continue
            relative = path.relative_to(game).as_posix()
            if not any(_matches_scope(relative, g) for r in rules for g in r['include_globs']):
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(game) or any(_excluded(part) for part in resolved.relative_to(game).parts):
                continue
            stat = path.stat()
            result.append((relative, str(resolved), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    return result


def _check_budget(cancel, deadline):
    if cancel and cancel():
        raise RuleError("cancelled")
    if deadline is not None and time.monotonic() >= deadline:
        raise RuleError("budget")


def _literal(line: str, start: int, end: int) -> str:
    value = line[start:end]
    if not value or len(value) > MAX_LITERAL or value[0] not in '\"\'' or value[-1] != value[0] or value.startswith(value[0] * 3):
        raise RuleError("literal")
    tokens = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(line).readline):
            if token.type not in {tokenize.ENCODING, tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER, tokenize.COMMENT}:
                tokens.append(token)
    except (tokenize.TokenError, IndentationError):
        pass
    index = next((i for i, t in enumerate(tokens) if t.type == tokenize.STRING and t.start == (1, start) and t.end == (1, end)), None)
    if index is None:
        raise RuleError("literal")
    previous = tokens[index - 1] if index else None
    following = tokens[index + 1] if index + 1 < len(tokens) else None
    if previous and (previous.type == tokenize.STRING or (previous.type == tokenize.OP and previous.string not in {'(', '[', '{', ',', ':', '='})):
        raise RuleError("expression")
    if previous and previous.type == tokenize.NAME and previous.string in {'if', 'else', 'and', 'or', 'not', 'in', 'is', 'yield', 'return', 'await'}:
        raise RuleError("expression")
    if following and following.string not in {')', ']', '}', ',', ':'}:
        raise RuleError("expression")
    if following is None and previous and previous.string in {'(', '[', '{', ','}:
        # 参数/容器字面量没有右边界时，可能在下一物理行隐式拼接。
        raise RuleError("expression")
    tail = index + 1
    while tail < len(tokens) and tokens[tail].string in {')', ']', '}'}:
        tail += 1
    if tail < len(tokens) and tokens[tail].string in {'+', '-', '*', '/', '%', '.', '[', 'if', 'and', 'or'}:
        raise RuleError("expression")
    try:
        decoded = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        raise RuleError("literal") from None
    if not isinstance(decoded, str) or not decoded.strip() or '\x00' in decoded:
        raise RuleError("literal")
    return decoded


def _triple_state(line: str, state: str) -> tuple[str, bool]:
    # 跳过多行字符串和注释中的伪代码；普通引号内的三引号不改变状态。
    i, skip = 0, bool(state)
    while i < len(line):
        if state:
            end = line.find(state, i)
            if end < 0:
                return state, True
            i, state = end + 3, ''
            continue
        if line[i] == '#':
            break
        if line[i] in '\"\'':
            quote = line[i]
            if line.startswith(quote * 3, i):
                state, skip, i = quote * 3, True, i + 3
                continue
            i += 1
            while i < len(line):
                if line[i] == '\\':
                    i += 2
                elif line[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
        else:
            i += 1
    return state, skip


def compile_rule(rule):
    try:
        compiled = regex.compile(rule['pattern'], regex.IGNORECASE if rule['flags'] else 0)
    except (regex.error, OverflowError, RuntimeError) as exc:
        raise RuleError("pattern", str(exc)) from exc
    group = rule['text_group']
    if (isinstance(group, str) and group not in compiled.groupindex) or (type(group) is int and group > compiled.groups):
        raise RuleError("group")
    return compiled


def literal_matches(rule, compiled, line):
    try:
        for match in compiled.finditer(line, timeout=MATCH_TIMEOUT):
            start, end = match.span(rule['text_group'])
            try:
                yield _literal(line, start, end), '', start, end
            except RuleError as exc:
                yield '', exc.code, start, end
    except TimeoutError as exc:
        raise RuleError("timeout", rule['id']) from exc


def line_matches(rule, compiled, line):
    for text, reason, _, _ in literal_matches(rule, compiled, line):
        yield text, reason


@dataclass(frozen=True)
class RuleCandidate:
    text: str
    path: str
    line: int
    rule_id: str
    start: int = 0
    end: int = 0
    raw_text: str = ""


class RuleScan:
    """仅在后台使用；继续扫描游标由此对象持有，不接受任意外部路径。"""
    def __init__(self, root: Path, profile: dict, cancel=None, *, base=None, paths=None):
        validate_profile(profile)
        self.root = Path(root).resolve()
        self.paths = {Path(p).resolve() for p in paths} if paths is not None else None
        self.base = Path(base).resolve() if base is not None else self.root / 'game'
        self.profile = copy.deepcopy(profile)
        self.rules = [r for r in self.profile['rules'] if r['enabled']]
        self.compiled = [(r, compile_rule(r)) for r in self.rules]
        self.manifest = None
        self.candidates: list[RuleCandidate] = []
        self.diagnostics = []
        self.filtered = self.raw_matches = self.bytes_read = self.files_read = 0
        self.completed, self.error = False, ''
        self.file_index = self.offset = self.line_number = 0
        self.triple = ''
        self.bracket_depth = self.candidate_chars = 0
        sample_deadline = time.monotonic() + 20
        for rule, compiled in self.compiled:
            _check_budget(cancel, sample_deadline)
            if not rule['positive_samples'] or not rule['negative_samples']:
                raise RuleError("samples")
            for positive, samples in ((True, rule['positive_samples']), (False, rule['negative_samples'])):
                for sample in samples:
                    _check_budget(cancel, sample_deadline)
                    matches = list(line_matches(rule, compiled, sample))
                    if (positive and (not matches or any(reason for _, reason in matches))) or (not positive and matches):
                        raise RuleError("samples", rule['id'])

    def verify_sources(self, cancel=None, deadline=None):
        if source_manifest(self.root, self.rules, cancel, deadline, base=self.base, paths=self.paths) != self.manifest:
            raise RuleError("stale")

    def advance(self, cancel=None, *, seconds=20.0, max_files=400, max_bytes=64 * 1024 * 1024):
        if self.error:
            raise RuleError(self.error)
        if self.completed:
            return
        deadline = time.monotonic() + seconds
        start_bytes, start_files = self.bytes_read, self.files_read
        try:
            if self.manifest is None:
                self.manifest = source_manifest(self.root, self.rules, cancel, deadline, base=self.base, paths=self.paths)
            else:
                self.verify_sources(cancel, deadline)
            while self.file_index < len(self.manifest):
                _check_budget(cancel, deadline)
                if self.files_read - start_files >= max_files or self.bytes_read - start_bytes >= max_bytes:
                    return
                relative, resolved, *_ = self.manifest[self.file_index]
                path = self.base / relative
                if str(path.resolve()) != resolved:
                    raise RuleError("stale")
                with path.open('rb') as stream:
                    stream.seek(self.offset)
                    while True:
                        _check_budget(cancel, deadline)
                        if self.bytes_read - start_bytes >= max_bytes:
                            return
                        raw = stream.readline(MAX_LINE + 1)
                        if not raw:
                            break
                        if len(raw) > MAX_LINE:
                            raise RuleError("long_line", relative)
                        line = raw.decode('utf-8-sig')
                        if self.profile.get('category') == 'tl':
                            self.bytes_read += len(raw)
                            self.offset, self.line_number = stream.tell(), self.line_number + 1
                            continue
                        self.triple, skip = _triple_state(line, self.triple)
                        previous_depth = self.bracket_depth
                        if not skip:
                            try:
                                for token in tokenize.generate_tokens(io.StringIO(line).readline):
                                    if token.type == tokenize.OP:
                                        if token.string in {'(', '[', '{'}:
                                            self.bracket_depth += 1
                                        elif token.string in {')', ']', '}'}:
                                            self.bracket_depth = max(0, self.bracket_depth - 1)
                            except (tokenize.TokenError, IndentationError):
                                pass
                        # 跨物理行的容器/调用无法确认相邻字符串边界，首版保守排除。
                        if not skip and not previous_depth and not self.bracket_depth:
                            for rule, compiled in self.compiled:
                                if not any(_matches_scope(relative, g) for g in rule['include_globs']):
                                    continue
                                for text, reason, start, end in literal_matches(rule, compiled, line):
                                    self.raw_matches += 1
                                    if reason:
                                        self.filtered += 1
                                        if len(self.diagnostics) < 200:
                                            self.diagnostics.append((relative, self.line_number + 1, reason))
                                    else:
                                        self.candidate_chars += len(text)
                                        if len(self.candidates) >= MAX_RESULTS or self.candidate_chars > 16 * 1024 * 1024:
                                            raise RuleError("result_limit")
                                        self.candidates.append(RuleCandidate(text, relative, self.line_number + 1, rule['id'], start, end, line[start + 1:end - 1]))
                        self.bytes_read += len(raw)
                        self.offset, self.line_number = stream.tell(), self.line_number + 1
                if self.profile.get('category') == 'tl':
                    from module.Extract.RpyExtractionSettings import ProfileTlExtractor
                    from module.Renpy.renpy_tl_core import parse_tl_document
                    if path.stat().st_size > 64 * 1024 * 1024:
                        raise RuleError('result_limit')
                    doc = parse_tl_document(path.read_text(encoding='utf-8-sig').splitlines())
                    for item in ProfileTlExtractor('custom', self.profile, cancel=cancel, deadline=deadline).extract(doc, relative):
                        _check_budget(cancel, None)
                        self.candidate_chars += len(item.get_src())
                        if len(self.candidates) >= MAX_RESULTS or self.candidate_chars > 16 * 1024 * 1024:
                            raise RuleError('result_limit')
                        self.raw_matches += 1
                        self.candidates.append(RuleCandidate(item.get_src(), relative, item.get_row(), ''))
                self.file_index += 1
                self.files_read += 1
                self.offset = self.line_number = 0
                self.triple = ''
                self.bracket_depth = 0
            self.verify_sources(cancel, deadline)
            self.completed = True
        except RuleError as exc:
            if exc.code == 'budget':
                return
            self.error = exc.code
            raise
        except (OSError, UnicodeError) as exc:
            self.error = 'read'
            raise RuleError('read', str(exc)) from exc
        finally:
            LogManager.get().info(f"游戏规则扫描: profile={self.profile['id']}, files={self.files_read}, bytes={self.bytes_read}, matches={self.raw_matches}, completed={self.completed}, error={self.error}")


def collect_game_rules(root: Path, cancel=None, *, profile=None) -> tuple[dict | None, list[RuleCandidate]]:
    """在写入 TL 之前完成规则快照扫描；失败则交由现有抽取事务处理。"""
    profile = profile if profile is not None else RuleStore().bound_profile(root)
    if not profile or not any(r['enabled'] for r in profile['rules']):
        return profile, []
    LogManager.get().info(f"加载游戏规则: project={project_key(root)}, profile={profile['id']}, digest={signature(profile)}")
    scan = RuleScan(root, profile, cancel)
    deadline = time.monotonic() + 300
    while not scan.completed:
        _check_budget(cancel, deadline)
        scan.advance(cancel)
    return profile, scan.candidates
