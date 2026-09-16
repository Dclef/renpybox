from module.ProgressBar import ProgressBar


class _FakeProgress:
    def __init__(self) -> None:
        self.calls = []

    def update(self, id, **kwargs) -> None:
        self.calls.append((id, kwargs))


def test_progress_bar_turns_absolute_completed_into_advance_samples():
    fake = _FakeProgress()
    original = ProgressBar.progress
    ProgressBar.progress = fake
    bar = ProgressBar(transient=True)
    bar.tasks[1] = {"running": True, "completed": 0}
    try:
        bar.update(1, total=10, completed=3)
        bar.update(1, total=10, completed=5)
    finally:
        ProgressBar.progress = original

    assert fake.calls == [
        (1, {"total": 10, "advance": 3, "remaining": "-:--:--"}),
        (1, {"total": 10, "advance": 2, "remaining": "-:--:--"}),
    ]


def test_progress_bar_calculates_remaining_time(monkeypatch):
    fake = _FakeProgress()
    original = ProgressBar.progress
    ProgressBar.progress = fake
    bar = ProgressBar(transient=True)
    bar.tasks[1] = {"running": True, "completed": 0, "started_at": 100.0}
    monkeypatch.setattr("module.ProgressBar.time.monotonic", lambda: 110.0)
    try:
        bar.update(1, total=100, completed=25)
    finally:
        ProgressBar.progress = original

    assert fake.calls == [
        (1, {"total": 100, "advance": 25, "remaining": "0:00:30"}),
    ]
