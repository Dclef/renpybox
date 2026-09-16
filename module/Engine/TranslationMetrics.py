"""Bounded, content-free telemetry for one translation session.

Durations are sums of work, not a partition of wall time: concurrent requests
overlap. Percentiles describe the most recent SAMPLE_LIMIT observations.
"""

from collections import deque
import json
import math
from pathlib import Path
import threading
import time
import uuid


SAMPLE_LIMIT = 2048
REQUEST_COUNTERS = (
    "logical_request_count", "provider_attempt_count", "http_attempt_count",
    "http_error_count", "http_429_count", "http_5xx_count", "transport_error_count",
    "logical_failure_count", "cancelled_request_count",
)
REQUEST_DURATIONS = ("retry_wait_ms", "provider_ms", "http_headers_ms", "http_body_ms")
REQUEST_SAMPLES = (
    "logical_request_ms_samples", "http_headers_ms_samples", "first_content_ms_samples",
)
STAGE_DURATIONS = (
    "slot_wait_ms", "rate_wait_ms", "executor_queue_ms", "task_prepare_ms",
    "task_local_ms", "decode_check_ms", "cache_save_ms",
)


def merge_request_metrics(target: dict, incoming: dict) -> None:
    """Combine snapshots, keeping counts exact and latency storage bounded."""
    for key in REQUEST_COUNTERS + REQUEST_DURATIONS:
        target[key] = target.get(key, 0) + incoming.get(key, 0)
    observed = incoming.get("logical_request_count", 0)
    if observed:
        target["http_observed_logical_count"] = target.get("http_observed_logical_count", 0) + incoming.get(
            "http_observed_logical_count",
            observed if incoming.get("http_observation_supported") is True else 0,
        )
    for key in REQUEST_SAMPLES:
        values = incoming.get(key, [])
        target[key] = (target.get(key, []) + list(values))[-SAMPLE_LIMIT:]


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[max(0, math.ceil(len(values) * quantile) - 1)], 3)


class TranslationMetrics:
    """Owned by one run; late workers can never mutate a subsequent run."""

    def __init__(self) -> None:
        self.session_id = uuid.uuid4().hex
        self.started = time.perf_counter()
        self.finished: float | None = None
        self._lock = threading.Lock()
        self._totals: dict = {}
        self._samples = {key: deque(maxlen=SAMPLE_LIMIT) for key in REQUEST_SAMPLES}
        # Only item object identities, never source/target text or file paths.
        self._successful_items: set[int] = set()

    def record_stages(self, **durations: float) -> None:
        with self._lock:
            if self.finished is not None:
                return
            for key, value in durations.items():
                if key in STAGE_DURATIONS:
                    self._totals[key] = self._totals.get(key, 0) + max(0, value)

    def record_cache_save(self, event: dict) -> None:
        with self._lock:
            if self.finished is not None:
                return
            for key in ("cache_save_count", "cache_save_error_count", "cache_save_ms"):
                self._totals[key] = self._totals.get(key, 0) + event.get(key, 0)

    def record_task(self, result: dict) -> None:
        with self._lock:
            if self.finished is not None:
                return
            request = result.get("request_metrics") or {}
            merge_request_metrics(self._totals, {k: v for k, v in request.items() if k not in REQUEST_SAMPLES})
            # merge_request_metrics adds empty arrays; don't persist redundant copies.
            for key in REQUEST_SAMPLES:
                self._totals.pop(key, None)
                self._samples[key].extend(request.get(key, []))
            if not request.get("logical_request_ms_samples") and result.get("latency_ms"):
                self._samples["logical_request_ms_samples"].append(float(result["latency_ms"]))
            for key in ("input_tokens", "output_tokens", "failed_line_count", "fallback_line_count", "line_count_mismatch_count", "requested_line_count"):
                self._totals[key] = self._totals.get(key, 0) + int(result.get(key, 0) or 0)
            for key in ("task_local_ms", "decode_check_ms"):
                self._totals[key] = self._totals.get(key, 0) + max(0, result.get(key, 0))
            self._totals["task_count"] = self._totals.get("task_count", 0) + 1
            self._totals["task_error_count"] = self._totals.get("task_error_count", 0) + int(bool(result.get("error")))
            if result.get("cancelled"):
                # A task may be cancelled before it creates a requester, so
                # preserve one cancellation in the run report in that case.
                if not request.get("cancelled_request_count"):
                    self._totals["cancelled_request_count"] = self._totals.get("cancelled_request_count", 0) + 1
            if not result.get("cancelled") and not result.get("error"):
                self._successful_items.update(result.get("effective_item_ids", []))

    def snapshot(self, *, finish: bool = False) -> dict:
        with self._lock:
            if finish and self.finished is None:
                self.finished = time.perf_counter()
            elapsed = max(0, (self.finished if self.finished is not None else time.perf_counter()) - self.started)
            result = {key: self._totals.get(key, 0) for key in REQUEST_COUNTERS + REQUEST_DURATIONS + STAGE_DURATIONS}
            result.update(self._totals)
            result.update(
                schema_version=1,
                session_id=self.session_id,
                elapsed_seconds=round(elapsed, 3),
                effective_item_count=len(self._successful_items),
                effective_items_per_minute=round(len(self._successful_items) * 60 / elapsed, 3) if elapsed > 0 else 0,
                percentile_scope="latest_samples",
                sample_limit=SAMPLE_LIMIT,
                http_observation_complete=(
                    result["logical_request_count"] > 0
                    and self._totals.get("http_observed_logical_count", 0) == result["logical_request_count"]
                ),
            )
            for key, values in self._samples.items():
                name = key.removesuffix("_samples")
                result[name + "_sample_count"] = len(values)
                result[name + "_p50"] = _percentile(list(values), 0.5)
                result[name + "_p95"] = _percentile(list(values), 0.95)
            for key in REQUEST_DURATIONS + STAGE_DURATIONS:
                result[key] = round(result[key], 3)
            return result

    def write_report(self, output_folder: str, *, status: str, settings: dict) -> Path:
        """Atomic export of an allowlisted report; never serialize runtime config."""
        report = self.snapshot(finish=True)
        report["status"] = status
        report["settings"] = {key: settings[key] for key in (
            "max_batch_lines", "max_batch_source_tokens", "max_output_tokens", "max_workers", "rpm_threshold",
        ) if key in settings}
        directory = Path(output_folder) / ".renpybox_metrics"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"translation-throughput-{self.session_id}.json"
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return path
