"""Benchmark translation batching and (optionally) provider throughput.

The default mode only runs the production cache chunker.  Network requests are
possible only when ``--execute`` is supplied explicitly.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import math
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Mapping

# Running ``python scripts/<tool>.py`` places only ``scripts`` on sys.path.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Engine.TaskLimiter import TaskLimiter
from module.Engine.Translator.TranslatorTask import TranslatorTask


PROFILES: tuple[tuple[str, int, int], ...] = (
    ("legacy10", 10, 0),
    ("source1024", 10, 1024),
    ("balanced20", 20, 1024),
)
_PROFILE_MAP = {name: (name, lines, source) for name, lines, source in PROFILES}
_SAFE_METRIC_KEYS = frozenset({
    "logical_request_count",
    "logical_request_ms",
    "provider_attempt_count",
    "provider_ms",
    "provider_total_ms",
    "retry_wait_ms",
    "http_attempt_count",
    "http_error_count",
    "http_429_count",
    "http_5xx_count",
    "transport_error_count",
    "logical_failure_count",
    "cancelled_request_count",
    "http_headers_ms",
    "http_body_ms",
    "http_headers_ms_samples",
    "first_content_ms_samples",
    "logical_request_ms_samples",
})


@dataclasses.dataclass(frozen=True)
class CorpusAudit:
    """Validated corpus data and counts safe to include in a report."""

    texts: tuple[str, ...]
    supplied_count: int
    blank_skipped: int
    duplicate_removed: int
    selected_count: int


def _read_records(path: Path) -> list[Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open("r", encoding="utf-8-sig") as reader:
            payload = json.load(reader)
        if not isinstance(payload, list):
            raise ValueError("JSON corpus must be a top-level list of strings")
        return payload
    if suffix not in {".jsonl", ".ndjson"}:
        raise ValueError("corpus must use .json, .jsonl, or .ndjson")
    records: list[Any] = []
    with path.open("r", encoding="utf-8-sig") as reader:
        for line_number, line in enumerate(reader, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL record at line {line_number}") from exc
    return records


def load_corpus(path: str | Path, max_items: int | None = None) -> CorpusAudit:
    """Load JSON or JSONL, remove blank and exact duplicate entries.

    JSON is a list of strings.  JSONL/NDJSON accepts either a JSON string per
    line or an object with a string ``text`` field.  Dedupe happens before the
    optional ``max_items`` limit so selection is stable and reproducible.
    """

    records = _read_records(Path(path))
    texts: list[str] = []
    seen: set[str] = set()
    blank_skipped = 0
    duplicate_removed = 0
    for index, record in enumerate(records, 1):
        if isinstance(record, str):
            text = record
        elif Path(path).suffix.lower() in {".jsonl", ".ndjson"} and isinstance(record, dict):
            text = record.get("text")
            if not isinstance(text, str):
                raise ValueError(f"JSONL record {index} must be a string or object with string text")
        else:
            raise ValueError(f"corpus record {index} must be a string")
        if not text.strip():
            blank_skipped += 1
            continue
        if text in seen:
            duplicate_removed += 1
            continue
        seen.add(text)
        texts.append(text)

    if max_items is not None:
        if max_items < 0:
            raise ValueError("max_items must be non-negative")
        texts = texts[:max_items]
    return CorpusAudit(
        texts=tuple(texts),
        supplied_count=len(records),
        blank_skipped=blank_skipped,
        duplicate_removed=duplicate_removed,
        selected_count=len(texts),
    )


def build_items(texts: Iterable[str]) -> list[CacheItem]:
    """Create a fresh, isolated set of production cache items."""

    return [
        CacheItem(src=text, file_path="benchmark-corpus", row=index + 1)
        for index, text in enumerate(texts)
    ]


def _profile(value: str | tuple[str, int, int]) -> tuple[str, int, int]:
    if isinstance(value, tuple):
        if len(value) != 3:
            raise ValueError("profile tuple must contain name, line budget, source budget")
        return value
    try:
        return _PROFILE_MAP[value]
    except KeyError as exc:
        raise ValueError(f"unknown profile: {value}") from exc


def _copy_config(config: Config | None, *, line_budget: int, source_budget: int, output_tokens: int | None) -> Config:
    result = copy.deepcopy(config) if config is not None else Config()
    result.token_threshold = line_budget
    result.max_batch_source_tokens = source_budget
    if output_tokens is not None:
        if output_tokens < 0:
            raise ValueError("output token budget must be non-negative")
        result.max_output_tokens = output_tokens
    return result


def _numeric(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _add_numeric(target: dict[str, int | float], key: str, value: Any) -> None:
    number = _numeric(value)
    if number is not None:
        target[key] = target.get(key, 0) + number


def _collect_request_metrics(target: dict[str, Any], result: Mapping[str, Any]) -> None:
    """Aggregate only numeric requester fields and numeric sample arrays."""

    candidates: list[Mapping[str, Any]] = []
    for key in ("request_metrics", "last_request_metrics"):
        value = result.get(key)
        if isinstance(value, Mapping):
            candidates.append(value)
        elif isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, Mapping))
    for metrics in candidates:
        for key, value in metrics.items():
            if str(key) not in _SAFE_METRIC_KEYS:
                continue
            if isinstance(value, list):
                samples = target.setdefault(str(key), [])
                if isinstance(samples, list):
                    samples.extend(number for item in value if (number := _numeric(item)) is not None)
            else:
                _add_numeric(target, str(key), value)


def _quality(
    items: Iterable[CacheItem],
    selected_texts: Iterable[str],
    *,
    executed: bool,
    attempted_sources: Iterable[str] = (),
) -> dict[str, Any]:
    selected = set(selected_texts)
    if not executed:
        return {
            "available": False,
            "effective_unique": None,
            "quality_failed_unique": None,
            "remaining_unique": None,
        }
    passed: set[str] = set()
    processed = set(attempted_sources)
    for item in items:
        src = item.get_src() or ""
        dst = item.get_dst() or ""
        if Base.is_item_completed(item.get_status()) and dst.strip() and dst.strip() != src.strip():
            passed.add(src)
    failed = processed - passed
    return {
        "available": True,
        "effective_unique": len(passed),
        "quality_failed_unique": len(failed),
        "remaining_unique": len(selected - processed),
    }


def run_profile(
    texts: Iterable[str],
    profile: str | tuple[str, int, int],
    *,
    config: Config | None = None,
    execute: bool = False,
    repeat: int = 1,
    concurrency: int = 1,
    output_tokens: int | None = None,
    platform: dict[str, Any] | None = None,
    current_round: int = 0,
) -> dict[str, Any]:
    """Run one profile and return aggregate, text-free benchmark data."""

    name, line_budget, source_budget = _profile(profile)
    corpus = tuple(texts)
    if repeat < 1:
        raise ValueError("repeat must be at least one")
    if concurrency < 1:
        raise ValueError("concurrency must be at least one")
    if execute and platform is None:
        raise ValueError("execute mode requires a platform configuration")

    started = time.perf_counter()
    all_items: list[CacheItem] = []
    chunk_count = 0
    planned_line_count = 0
    planned_source_tokens = 0
    row_count = input_tokens = output_token_total = 0
    failed_line_count = 0
    task_count = 0
    errors = 0
    request_metrics: dict[str, Any] = {}
    attempted_sources: set[str] = set()
    futures: list[Future[Any]] = []

    def execute_task(task: TranslatorTask, limiter: TaskLimiter) -> tuple[Any, TranslatorTask]:
        try:
            return task.start(current_round), task
        finally:
            limiter.release()

    limiter = TaskLimiter(rps=concurrency, rpm=int(getattr(config or Config(), "rpm_threshold", 0) or 0), max_concurrency=concurrency) if execute else None
    with ThreadPoolExecutor(max_workers=concurrency) if execute else _NullExecutor() as executor:
        for _ in range(repeat):
            task_config = _copy_config(config, line_budget=line_budget, source_budget=source_budget, output_tokens=output_tokens)
            manager = CacheManager(service=False)
            items = build_items(corpus)
            all_items.extend(items)
            manager.set_items(items)
            chunks = manager.iter_item_chunks(
                line_budget,
                int(getattr(task_config, "preceding_lines_threshold", 0) or 0),
                source_token_limit=source_budget,
            )
            for chunk, precedings in chunks:
                chunk_count += 1
                planned_line_count += sum(
                    sum(1 for line in (item.get_src() or "").splitlines() if line.strip())
                    for item in chunk
                )
                planned_source_tokens += sum(item.get_token_count() for item in chunk)
                if not execute:
                    continue
                if not limiter.acquire():
                    errors += 1
                    continue
                if not limiter.wait():
                    limiter.release()
                    errors += 1
                    continue
                try:
                    attempted_sources.update(item.get_src() or "" for item in chunk)
                    task = TranslatorTask(
                        task_config,
                        platform,
                        False,
                        chunk,
                        precedings,
                        runtime_config=task_config,
                    )
                    # The production table contains source and destination text.
                    task.print_log_table = lambda *args, **kwargs: None
                    futures.append(executor.submit(execute_task, task, limiter))
                    task_count += 1
                except Exception:
                    limiter.release()
                    errors += 1

        if execute:
            for future in as_completed(futures):
                try:
                    result, task = future.result()
                except Exception:
                    errors += 1
                    continue
                if not isinstance(result, Mapping):
                    continue
                for key in ("row_count", "input_tokens", "output_tokens", "failed_line_count"):
                    value = _numeric(result.get(key))
                    if value is not None:
                        if key == "row_count":
                            row_count += int(value)
                        elif key == "input_tokens":
                            input_tokens += int(value)
                        elif key == "output_tokens":
                            output_token_total += int(value)
                        else:
                            failed_line_count += int(value)
                _collect_request_metrics(request_metrics, result)
                task_metrics = getattr(task, "last_request_metrics", None)
                if isinstance(task_metrics, Mapping):
                    _collect_request_metrics(request_metrics, {"last_request_metrics": task_metrics})

    elapsed_ms = (time.perf_counter() - started) * 1000
    quality = _quality(all_items, corpus, executed=execute, attempted_sources=attempted_sources)
    elapsed_minutes = elapsed_ms / 60000
    effective = quality.get("effective_unique")
    return {
        "profile": name,
        "repeat": repeat,
        "unique_input_count": len(set(corpus)),
        "planned_line_budget": line_budget,
        "planned_source_token_budget": source_budget,
        "output_token_budget": output_tokens if output_tokens is not None else int(getattr(config or Config(), "max_output_tokens", 0) or 0),
        "chunk_count": chunk_count,
        "planned_line_count": planned_line_count,
        "planned_source_tokens": planned_source_tokens,
        "average_chunk_lines": round(planned_line_count / chunk_count, 3) if chunk_count else 0,
        "average_chunk_source_tokens": round(planned_source_tokens / chunk_count, 3) if chunk_count else 0,
        "task_count": task_count,
        "row_count": row_count,
        "input_tokens": input_tokens,
        "output_tokens": output_token_total,
        "failed_line_count": failed_line_count,
        "errors": errors,
        "request_metrics": request_metrics,
        "elapsed_ms": round(elapsed_ms, 3),
        "quality": quality,
        "effective_unique_items_per_minute": round(effective / elapsed_minutes, 3) if execute and effective is not None and elapsed_minutes > 0 else None,
    }


class _NullExecutor:
    def __enter__(self) -> "_NullExecutor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure translation batching locally; provider calls require explicit --execute.",
        epilog="Corpus: .json is a list of strings. .jsonl/.ndjson accepts JSON strings or {\"text\": string} records.",
    )
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--profile", action="append", choices=tuple(_PROFILE_MAP), help="profile to run; repeat for multiple (default: all)")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--output", dest="output_tokens", type=int, default=None, help="override max output tokens")
    parser.add_argument("--execute", action="store_true", help="send requests to the configured provider")
    parser.add_argument("--config", type=Path, default=None, help="configuration JSON path for --execute")
    parser.add_argument("--platform-id", type=int, default=None)
    parser.add_argument("--report", type=Path, default=None, help="also write the JSON report to a local file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    audit = load_corpus(args.corpus, args.max_items)
    config: Config | None = None
    platform: dict[str, Any] | None = None
    if args.execute:
        config = Config().load(str(args.config) if args.config else None)
        platform_id = config.activate_platform if args.platform_id is None else args.platform_id
        platform = config.get_platform(platform_id)
        if not isinstance(platform, dict):
            raise SystemExit(f"no platform with id {platform_id}; use --platform-id or configure activate_platform")
    profiles = args.profile or [name for name, _, _ in PROFILES]
    reports = [
        run_profile(
            audit.texts,
            profile,
            config=config,
            execute=args.execute,
            repeat=args.repeat,
            concurrency=args.concurrency,
            output_tokens=args.output_tokens,
            platform=platform,
        )
        for profile in profiles
    ]
    payload = {
        "dry_run": not args.execute,
        "corpus": {
            "supplied_count": audit.supplied_count,
            "blank_skipped": audit.blank_skipped,
            "duplicate_removed": audit.duplicate_removed,
            "selected_count": audit.selected_count,
        },
        "profiles": reports,
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    print(encoded)
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
