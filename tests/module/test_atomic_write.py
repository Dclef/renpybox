import pytest

from module.File.AtomicWrite import atomic_write_text


def test_atomic_write_preserves_existing_file_when_validation_fails(tmp_path):
    target = tmp_path / "fictional.rpy"
    target.write_text("stable constellation\n", encoding="utf-8")

    def reject(_text: str) -> None:
        raise ValueError("fictional validation failure")

    with pytest.raises(ValueError, match="fictional validation failure"):
        atomic_write_text(target, "broken constellation\n", validator=reject)

    assert target.read_text(encoding="utf-8") == "stable constellation\n"
    assert list(tmp_path.glob("*.tmp")) == []
