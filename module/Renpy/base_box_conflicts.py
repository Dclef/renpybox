"""Plan base_box reconciliation without touching live files, then commit atomically.

Only template-owned string identities may be consolidated. Other duplicate runtime
identities fail closed. Backups and staging live outside Ren'Py's script tree.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import tokenize
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from module.Localizer.Localizer import Localizer
from module.Renpy.renpy_tl_core import (
    TlBlockKind, escape_tl_string, parse_tl_document, parse_tl_header, scan_quoted_literals,
)

MANAGED_NAMES = frozenset({"common_box.rpy", "screens_box.rpy", "style_box.rpy"})


def is_managed_template(path: Path | str) -> bool:
    parts = str(path).replace("\\", "/").split("/")
    return any(part.casefold() == "base_box" for part in parts[:-1])


class TranslationConflict(ValueError):
    def __init__(self, details: str):
        self.details = details
        super().__init__(Localizer.get().base_box_conflict.format(details=details))


@dataclass(frozen=True)
class Entry:
    path: Path
    language: str
    kind: str
    identity: str
    line: int
    end: int
    value: str
    new_line: int = 0
    literal: str = ""

    @property
    def key(self):
        return self.language, self.kind, self.identity

    @property
    def valid(self):
        return bool(self.value.strip()) and self.value != self.identity


def _unsafe(path, line):
    raise ValueError(Localizer.get().base_box_unsafe_syntax.format(path=path, line=line))


def _literal_token(code: str, path: Path, line: int) -> str:
    try:
        tokens = [t for t in tokenize.generate_tokens(io.StringIO(code).readline)
                  if t.type not in (tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER,
                                    tokenize.COMMENT)]
        if len(tokens) != 1 or tokens[0].type != tokenize.STRING:
            _unsafe(path, line)
        token = tokens[0].string
        literal = token[1:] if token.startswith("r") else token
        if not literal or literal[0] not in "\"'" or literal.startswith(literal[0] * 3):
            _unsafe(path, line)
        return token
    except (SyntaxError, tokenize.TokenError, IndentationError):
        _unsafe(path, line)


def _literal(code: str, path: Path, line: int) -> str:
    token = _literal_token(code, path, line)
    raw = token.startswith("r")
    literal = token[1:] if raw else token
    # Reuse the shared scanner for ordinary TL double-quoted literals. Single
    # quotes are tokenized above because the shared TL scanner only emits ".
    inner = (scan_quoted_literals(literal)[0].raw_inner if literal.startswith('"')
             else literal[1:-1])
    if raw:
        return inner
    # Ren'Py lexer.string collapses unescaped spaces BEFORE decoding escapes.
    # Python literal_eval differs for \t, \r, \[, \{, \% and short \u escapes.
    collapsed = []
    for char in inner:
        if char in " \n":
            if not collapsed or collapsed[-1] != " ":
                collapsed.append(" ")
        else:
            collapsed.append(char)
    value = []
    index = 0
    while index < len(collapsed):
        char = collapsed[index]
        index += 1
        if char != "\\":
            value.append(char)
            continue
        if index == len(collapsed):
            _unsafe(path, line)
        char = collapsed[index]
        index += 1
        if char == "u":
            digits = []
            while index < len(collapsed) and len(digits) < 4 and collapsed[index] in "0123456789abcdefABCDEF":
                digits.append(collapsed[index])
                index += 1
            value.append(chr(int("".join(digits), 16)) if digits else "u")
        else:
            value.append("\n" if char == "n" else char * 2 if char in "[{%" else char)
    return "".join(value)


def _parse_lines(lines):
    # Keep shared parser positions while accepting legal trailing header comments.
    normalized = []
    for line in lines:
        header = line.split("#", 1)[0].rstrip()
        normalized.append(header if parse_tl_header(header) is not None else line)
    return parse_tl_document(normalized)


def entries(path: Path, text: str) -> list[Entry]:
    """Use shared TL blocks and line positions, bounded by real indentation."""
    lines = text.splitlines()
    document = _parse_lines(lines)
    result = []
    for block in document.blocks:
        start = block.header_line_no
        end = start
        while end < len(lines):
            raw = lines[end]
            if raw.strip() and not raw.lstrip().startswith("#") and not raw[0].isspace():
                break
            end += 1
        if block.kind == TlBlockKind.STRINGS:
            pending = None
            for index in range(start, end):
                code = lines[index].strip()
                if not code or code.startswith("#"):
                    continue
                parts = code.split(None, 1)
                keyword, rest = parts[0], parts[1] if len(parts) > 1 else ""
                if keyword == "old":
                    if pending is not None:
                        _unsafe(path, index + 1)
                    pending = (index + 1, _literal(rest.strip(), path, index + 1))
                elif keyword == "new":
                    if pending is None:
                        _unsafe(path, index + 1)
                    old_line, old = pending
                    result.append(Entry(path, block.lang, "strings", old, old_line,
                                        index + 1, _literal(rest.strip(), path, index + 1), index + 1,
                                        _literal_token(rest.strip(), path, index + 1)))
                    pending = None
                elif code != "pass":
                    _unsafe(path, index + 1)
            if pending is not None:
                _unsafe(path, pending[0])
        elif block.label not in {"python", "style", "default"}:
            # Label uniqueness is language-global, never relative-file scoped.
            body = "\n".join(line.strip() for line in lines[start:end]
                             if line.strip() and not line.lstrip().startswith("#"))
            result.append(Entry(path, block.lang, "label", block.label,
                                block.header_line_no, end, body))
    return result


def render_templates(source: Path, language: str) -> dict[Path, str]:
    result = {}
    if not language or not language.isidentifier():
        raise ValueError(language)
    for path in sorted(Path(source).glob("*.rpy")):
        content = path.read_text(encoding="utf-8-sig")
        content = content.replace("translate schinese", f"translate {language}")
        content = content.replace("tl/schinese", f"tl/{language}")
        content = content.replace("{tl_name}", language)
        content = content.replace("{font_path}", f"tl/{language}/fonts/SourceHanSansCN-Bold.ttf")
        content = content.replace("{is_rtl_enabled}", "False")
        result[Path("base_box") / path.name] = content
    return result


def default_templates(language: str) -> dict[Path, str]:
    from base.PathHelper import get_resource_path
    source = Path(get_resource_path("resource", "base_box"))
    return render_templates(source, language) if source.is_dir() else {}


def read_tree(root: Path) -> dict[Path, str]:
    root = Path(root)
    return {path.relative_to(root): path.read_bytes().decode("utf-8-sig")
            for path in sorted(root.rglob("*.rpy")) if path.is_file()}


def source_tree(tl_dir: Path) -> dict[Path, str]:
    """Read game scripts outside tl; they are immutable reservations, never writes."""
    tl_dir = Path(tl_dir)
    if tl_dir.parent.name.casefold() != "tl":
        return {}
    game = tl_dir.parent.parent
    result = {}
    for path in sorted(game.rglob("*.rpy")):
        rel = path.relative_to(game)
        if rel.parts[0].casefold() in {"tl", "fonts_backup", ".renpybox"}:
            continue
        if path.is_file():
            result[Path("@game") / rel] = path.read_bytes().decode("utf-8-sig")
    return result


def _remove_entry(lines: list[str], entry: Entry, removed: set[int]):
    if entry.kind == "strings":
        # Keep all comments, including comments between old/new and inline notes.
        for index in (entry.line - 1, entry.new_line - 1):
            raw = lines[index]
            try:
                notes = [token.string for token in tokenize.generate_tokens(io.StringIO(raw.strip()).readline)
                         if token.type == tokenize.COMMENT]
            except tokenize.TokenError:
                notes = []
            if notes:
                indent = raw[:len(raw) - len(raw.lstrip())]
                lines[index] = indent + notes[0]
            else:
                removed.add(index)
    else:
        for index in range(entry.line - 1, entry.end):
            if lines[index].strip() and not lines[index].lstrip().startswith("#"):
                removed.add(index)


def _finish_lines(lines: list[str], removed: set[int], newline: str) -> str:
    result = [line for index, line in enumerate(lines) if index not in removed]
    # An empty strings suite is invalid Ren'Py. Remove just its header, never
    # an unrelated screen/label or comments sharing that file.
    document = _parse_lines(result)
    drop = set()
    for block in document.blocks:
        if block.kind != TlBlockKind.STRINGS:
            continue
        index = block.header_line_no
        active = False
        while index < len(result):
            raw = result[index]
            if raw.strip() and not raw.lstrip().startswith("#"):
                if not raw[0].isspace():
                    break
                active = True
            index += 1
        if not active:
            index = block.header_line_no - 1
            if "#" in result[index]:
                result[index] = "#" + result[index].split("#", 1)[1]
            else:
                drop.add(index)
    return newline.join(line for index, line in enumerate(result) if index not in drop)


def coordinate(files: Mapping[Path, str], *, templates: Mapping[Path, str] | None = None,
               readonly: Mapping[Path, str] | None = None,
               historical: Mapping[Path, str] | None = None,
               incoming_prefix: str | None = None) -> tuple[dict[Path, str], int]:
    """Return a pure plan. Incoming duplicates are only permitted as merge input.

    Existing managed values matching the shipped template are defaults. Any
    differing managed value is a user value and receives the same protection as
    translations outside base_box. Two distinct user values never pick a winner.
    """
    texts = dict(files)
    readonly = dict(readonly or {})
    template_values = defaultdict(set)
    for path, text in (templates or {}).items():
        for item in entries(path, text):
            template_values[item.key].add(item.value)
    groups = defaultdict(list)
    for path, text in {**texts, **readonly}.items():
        for item in entries(path, text):
            groups[item.key].append(item)
    managed_keys = {item.key for group in groups.values() for item in group
                    if is_managed_template(item.path)}
    for path, text in (historical or {}).items():
        for item in entries(path, text):
            if item.key in managed_keys:
                groups[item.key].append(item)
    lines = {path: text.splitlines() for path, text in texts.items()}
    removed = defaultdict(set)
    changed = set()
    count = 0
    conflicts = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        related = key in managed_keys
        incoming = lambda item: incoming_prefix and item.path.parts[0] == incoming_prefix
        if not related:
            # A prospective incremental merge may update one label in the same
            # relative file; labels in different files still conflict globally.
            main = [item for item in group if not incoming(item)]
            delta = [item for item in group if incoming(item)]
            valid_merge = bool(delta) and len(main) <= 1 and len(delta) == 1
            if valid_merge and key[1] == "label" and main:
                valid_merge = Path(*delta[0].path.parts[1:]) == main[0].path
            if valid_merge and key[1] == "strings":
                valid_merge = len({item.value for item in group if item.valid}) <= 1
            if valid_merge:
                continue
            conflicts.append(group)
            continue
        user_values = {item.value for item in group if item.valid and not (
            is_managed_template(item.path) and item.value in template_values.get(key, set()))}
        if len(user_values) > 1:
            conflicts.append(group)
            continue
        immutable = [item for item in group if item.path in readonly]
        if len(immutable) > 1:
            conflicts.append(group)
            continue
        preferred = next(iter(user_values), None)
        if preferred is None:
            preferred = next((item.value for item in group if item.valid), group[0].value)
        winner = (immutable or [item for item in group if is_managed_template(item.path)
                               and not incoming(item)] or group)[0]
        if winner.path in readonly and winner.value != preferred:
            conflicts.append(group)
            continue
        if key[1] == "label" and len({item.value for item in group}) > 1:
            conflicts.append(group)
            continue
        if winner.value != preferred:
            raw = lines[winner.path][winner.new_line - 1]
            indent = raw[:len(raw) - len(raw.lstrip())]
            note = next((t.string for t in tokenize.generate_tokens(io.StringIO(raw.strip()).readline)
                         if t.type == tokenize.COMMENT), "")
            donor = next(item for item in group if item.value == preferred)
            literal = donor.literal or f'"{escape_tl_string(preferred)}"'
            lines[winner.path][winner.new_line - 1] = (
                f"{indent}new {literal}" + (f"  {note}" if note else ""))
            changed.add(winner.path)
        for item in group:
            if item is winner or item.path not in texts:
                continue
            _remove_entry(lines[item.path], item, removed[item.path])
            changed.add(item.path)
            count += 1
    if conflicts:
        details = "; ".join(
            f"{group[0].language}/{group[0].kind}/{group[0].identity!r}: "
            + ", ".join(f"{item.path}:{item.line}" for item in group)
            for group in conflicts)
        raise TranslationConflict(details)
    for path in changed:
        newline = "\r\n" if "\r\n" in texts[path] else "\n"
        texts[path] = _finish_lines(lines[path], removed[path], newline) + newline
    return texts, count


def plan_tree(tl_dir: Path, proposed: Mapping[Path, str | None] | None = None,
              *, templates=None, readonly=None) -> tuple[dict[Path, bytes | None], int]:
    current = read_tree(tl_dir)
    final = dict(current)
    for path, text in (proposed or {}).items():
        if text is None:
            final.pop(path, None)
        else:
            final[path] = text
    language = Path(tl_dir).name
    defaults = default_templates(language) if templates is None else templates
    # A full-file output can hide a pre-existing manual template-related value.
    # Compare those replaced entries too, before the overlay forgets their bytes.
    previous = {Path("@previous") / path: text for path, text in current.items()
                if path in (proposed or {}) and not is_managed_template(path)}
    final, removed = coordinate(final, templates=defaults, historical=previous,
                                readonly=source_tree(tl_dir) if readonly is None else readonly)
    changes = {}
    for path in sorted(set(current) | set(final)):
        before, after = current.get(path), final.get(path)
        if before != after:
            changes[Path(tl_dir) / path] = after.encode("utf-8") if after and after.strip() else None
    return changes, removed


def add_compiled_cleanup(changes: dict[Path, bytes | None], tl_dir: Path):
    for path in list(changes):
        if path.suffix.casefold() == ".rpy":
            compiled = path.with_suffix(".rpyc")
            if compiled.exists():
                changes[compiled] = None
    # Only known tool-owned orphan artifacts, never every rpyc in a game.
    for name in MANAGED_NAMES:
        source = Path(tl_dir) / "base_box" / name
        compiled = source.with_suffix(".rpyc")
        if compiled.exists():
            changes[compiled] = None


class TransactionFailure(RuntimeError):
    def __init__(self, error, rollback, backup):
        self.rollback_failed = bool(rollback)
        self.backup_path = str(backup) if rollback else None
        super().__init__(Localizer.get().base_box_transaction_failed.format(
            error=error, rollback="; ".join(rollback), backup=self.backup_path or ""))


def commit_changes(changes: Mapping[Path, bytes | None], *, allowed_roots,
                   expected: Mapping[Path, bytes | None] | None = None) -> int:
    """Back up the entire write set before writing; restore bytes and metadata.

    A rollback failure keeps the recoverable .bak files in the system temporary
    directory and reports the path. Successful rollback removes newly made dirs.
    """
    from module.File.AtomicWrite import validate_write_path
    resolved = {}
    for path, value in changes.items():
        path = Path(path)
        validate_write_path(path, allowed_roots)
        target = path.resolve()
        if target.exists() and not target.is_file():
            raise ValueError(str(path))
        if target in resolved and resolved[target] != value:
            raise TranslationConflict(str(path))
        resolved[target] = value
    if expected is not None:
        for path, value in expected.items():
            actual = Path(path).read_bytes() if Path(path).is_file() else None
            if actual != value:
                raise TranslationConflict(str(path))
    if not resolved:
        return 0
    backup_root = Path(tempfile.mkdtemp(prefix="renpybox-transaction-"))
    backups = {}
    applied = []
    made_dirs = set()
    rollback = []
    temp_paths = []
    try:
        for index, target in enumerate(resolved):
            backup = backup_root / f"{index}-{target.name}.bak"
            if target.exists():
                shutil.copy2(target, backup)
                backups[target] = backup
            else:
                backups[target] = None
        (backup_root / "manifest.json").write_text(json.dumps(
            {str(target): str(backup) if backup else None for target, backup in backups.items()},
            ensure_ascii=False, indent=2), encoding="utf-8")
        for target, value in resolved.items():
            if value is None:
                if target.exists():
                    target.unlink()
                    applied.append(target)
                continue
            parent = target.parent
            while not parent.exists():
                made_dirs.add(parent)
                parent = parent.parent
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            temp = Path(name)
            temp_paths.append(temp)
            with os.fdopen(fd, "wb") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            if target.exists():
                shutil.copymode(target, temp)
            os.replace(str(temp), str(target))
            applied.append(target)
        return len(applied)
    except Exception as exc:
        for target in reversed(applied):
            try:
                backup = backups[target]
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    # Copy to sibling, then replace so even rollback is atomic.
                    fd, name = tempfile.mkstemp(prefix=".rollback-", suffix=".tmp", dir=target.parent)
                    os.close(fd)
                    temp = Path(name)
                    temp_paths.append(temp)
                    shutil.copy2(backup, temp)
                    os.replace(str(temp), str(target))
            except Exception as restore_error:
                rollback.append(f"{target}: {restore_error}")
        raise TransactionFailure(exc, rollback, backup_root) from exc
    finally:
        for temp in temp_paths:
            temp.unlink(missing_ok=True)
        for directory in sorted(made_dirs, key=lambda p: len(p.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        if not rollback:
            shutil.rmtree(backup_root, ignore_errors=True)


def injection_plan(tl_dir: Path, language: str, template_dir: Path):
    current = read_tree(tl_dir)
    templates = render_templates(template_dir, language)
    proposed = {path: text for path, text in templates.items() if path not in current}
    # Existing managed files keep manual edits; append only globally missing keys.
    have = {item.key for path, text in current.items() if is_managed_template(path)
            for item in entries(path, text)}
    for path, template in templates.items():
        if path not in current:
            continue
        missing = [item for item in entries(path, template) if item.key not in have]
        if missing:
            text = current[path]
            template_lines = template.splitlines()
            for item in missing:
                if item.kind == "strings":
                    text += (f"\ntranslate {item.language} strings:\n"
                             + "\n".join(template_lines[item.line - 1:item.end]) + "\n")
                else:
                    text += "\n" + "\n".join(template_lines[item.line - 1:item.end]) + "\n"
            proposed[path] = text
    changes, removed = plan_tree(tl_dir, proposed, templates=templates)
    add_compiled_cleanup(changes, tl_dir)
    return changes, removed


def inject_base_box(tl_dir: Path, language: str, template_dir: Path,
                    *, extra_files: Mapping[Path, bytes] | None = None) -> int:
    tl_dir = Path(tl_dir)
    changes, _ = injection_plan(tl_dir, language, template_dir)
    if extra_files is None:
        # Extraction now shares the whole template pack, including style_box.
        # Supply its missing font dependencies without replacing user assets.
        font_dir = Path(template_dir).parent / "fonts"
        extra_files = {Path("fonts") / font.name: font.read_bytes()
                       for font in font_dir.glob("*")
                       if font.is_file() and font.suffix.lower() in {".ttf", ".otf", ".ttc", ".otc"}
                       and not (tl_dir / "fonts" / font.name).exists()}
    for path, content in extra_files.items():
        target = tl_dir / path
        if not target.is_file() or target.read_bytes() != content:
            changes[target] = content
    commit_changes(changes, allowed_roots=[tl_dir])
    return len(list((tl_dir / "base_box").glob("*.rpy")))


def merge_incremental_transactionally(extractor, game_dir, language, tl_dir,
                                     incremental_dir, *, clean_duplicates, config_snapshot):
    """Run the existing identity-aware merger on isolated copies, then commit."""
    from module.Extract.UnifiedExtractor import ExtractionResult
    from module.Renpy.renpy_extract import ExtractionCancelled
    from module.Extract.ReplaceGenerator import declined_candidates_path, record_declined_candidates
    tl_dir, incremental_dir = Path(tl_dir), Path(incremental_dir)
    try:
        target_root, incoming_root = tl_dir.resolve(), incremental_dir.resolve()
        if (target_root == incoming_root or target_root in incoming_root.parents
                or incoming_root in target_root.parents):
            raise TranslationConflict(f"{tl_dir}; {incremental_dir}")
        current = read_tree(tl_dir)
        declined = extractor._collect_declined_candidates_from_cycle(game_dir, language, incremental_dir)
        incoming = {path: text for path, text in read_tree(incremental_dir).items()
                    if not is_managed_template(path)}
        templates = default_templates(language)
        reserved = source_tree(tl_dir)
        # Check all existing duplicates before any legacy cleanup could choose
        # an arbitrary first user translation. Resolve only template identities.
        current, _ = coordinate(current, templates=templates, readonly=reserved)
        combined = {**current, **{Path("@incoming") / path: text
                                for path, text in incoming.items()}}
        combined, _ = coordinate(combined, templates=templates, readonly=reserved,
                                 incoming_prefix="@incoming")
        expected = {path: path.read_bytes() for root in (tl_dir, incremental_dir)
                    for path in root.rglob("*") if path.is_file()
                    and path.suffix.lower() in {".rpy", ".rpyc"}}
        with tempfile.TemporaryDirectory(prefix="renpybox-merge-") as staging:
            root = Path(staging)
            target = root / language
            delta = root / "incoming" / incremental_dir.name
            target.mkdir()
            delta.mkdir(parents=True)
            if (incremental_dir / "cache").is_dir():
                (delta / "cache").mkdir()
            for path, text in combined.items():
                if path.parts[0] == "@incoming":
                    dest = delta / Path(*path.parts[1:])
                else:
                    dest = target / path
                if not text.strip():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(text.encode("utf-8"))
            result = extractor.merge_incremental_folder(
                game_dir, language, delta, clean_duplicates=clean_duplicates,
                config_snapshot=config_snapshot, target_tl_dir=target, _staged=True)
            result.tl_dir, result.incremental_dir = tl_dir, incremental_dir
            if not result.success:
                return result
            final = read_tree(target)
            proposed = {path: final.get(path) for path in set(read_tree(tl_dir)) | set(final)}
            changes, _ = plan_tree(tl_dir, proposed, templates=templates, readonly=reserved)
            add_compiled_cleanup(changes, tl_dir)
            # Retire only the scripts that this successful merge consumed. Keep
            # cache, unrelated binaries and compiled-only files intact.
            for path in incremental_dir.rglob("*.rpy"):
                changes[path] = None
                if path.with_suffix(".rpyc").is_file():
                    changes[path.with_suffix(".rpyc")] = None
            allowed_roots = [tl_dir, incremental_dir]
            if declined:
                metadata = declined_candidates_path(game_dir, language)
                staged_project = root / "metadata-project"
                staged_metadata = declined_candidates_path(staged_project, language)
                expected[metadata] = metadata.read_bytes() if metadata.is_file() else None
                if expected[metadata] is not None:
                    staged_metadata.parent.mkdir(parents=True, exist_ok=True)
                    staged_metadata.write_bytes(expected[metadata])
                record_declined_candidates(staged_project, language, declined)
                if staged_metadata.is_file() and staged_metadata.read_bytes() != expected[metadata]:
                    changes[metadata] = staged_metadata.read_bytes()
                    allowed_roots.append(metadata.parent)
            extractor._check_cancel()
            commit_changes(changes, allowed_roots=allowed_roots, expected=expected)
        for directory in sorted(incremental_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if directory.is_dir() and directory.name != "cache":
                try:
                    directory.rmdir()
                except OSError:
                    pass
        try:
            incremental_dir.rmdir()
        except OSError:
            pass
        return result
    except Exception as exc:
        return ExtractionResult(success=False, message=str(exc), tl_dir=tl_dir,
                                incremental_dir=incremental_dir,
                                cancelled=isinstance(exc, ExtractionCancelled))
