import json

from module.Engine.TranslationMetrics import TranslationMetrics


def test_metrics_are_bounded_and_compute_effective_rate(tmp_path):
    metrics = TranslationMetrics()
    metrics.record_task({
        "request_metrics": {
            "logical_request_count": 2,
            "provider_attempt_count": 3,
            "provider_ms": 120,
            "logical_request_ms_samples": [10, 20],
        },
        "effective_item_ids": [1, 2],
        "requested_line_count": 2,
    })
    snapshot = metrics.snapshot()
    assert snapshot["logical_request_count"] == 2
    assert snapshot["provider_attempt_count"] == 3
    assert snapshot["effective_item_count"] == 2
    assert snapshot["logical_request_ms_p50"] == 10
    assert snapshot["logical_request_ms_p95"] == 20

    path = metrics.write_report(str(tmp_path), status="completed", settings={"max_workers": 4})
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert "source" not in json.dumps(report)
    assert report["settings"] == {"max_workers": 4}


def test_finished_metrics_ignore_late_workers():
    metrics = TranslationMetrics()
    metrics.snapshot(finish=True)
    metrics.record_task({"effective_item_ids": [99], "request_metrics": {"logical_request_count": 1}})
    snapshot = metrics.snapshot()
    assert snapshot["logical_request_count"] == 0
    assert snapshot["effective_item_count"] == 0
