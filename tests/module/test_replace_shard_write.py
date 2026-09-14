from pathlib import Path
from types import SimpleNamespace

import pytest

from module.Extract import ReplaceGenerator as generator


def _run_hook(path, text):
    namespace = {
        "config": SimpleNamespace(replace_text=None, tl_directory="tl"),
        "renpy": SimpleNamespace(
            file=lambda resource: (path.parent.parent.parent / resource).open("rb")
        ),
    }
    script = path.read_text(encoding="utf-8")
    exec(script.replace("translate chinese python:", "if True:"), namespace)
    return namespace["config"].replace_text(text)


@pytest.fixture
def previous_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "REPLACE_SHARD_BYTES", 100)
    output = tmp_path / "game" / "tl" / "chinese" / "replace_text_auto.rpy"
    pairs = [(f"Old field {index}: [value]", f"Old value {index}: [value]") for index in range(4)]
    generator.write_replace_script(output, pairs)
    output.with_suffix(".rpyc").write_bytes(b"previous compiled hook")
    data_dir = output.parent / generator.REPLACE_DATA_DIR
    assert len(list(data_dir.glob("*.json"))) > 1
    assert _run_hook(output, "Old field 3: 27") == "Old value 3: 27"
    return output, pairs


@pytest.mark.parametrize("failure", ["shard", "entry", "inline_entry"])
def test_failed_hook_update_keeps_previous_entry_and_shards(previous_hook, monkeypatch, failure):
    output, old_pairs = previous_hook
    previous_script = output.read_bytes()
    data_dir = output.parent / generator.REPLACE_DATA_DIR
    previous_data = {path: path.read_bytes() for path in data_dir.glob("*.json")}
    real_write = generator.atomic_write_text
    shard_writes = 0

    def fail_write(path, text, **kwargs):
        nonlocal shard_writes
        path = Path(path)
        if path.suffix == ".json":
            shard_writes += 1
            if failure == "shard" and shard_writes == 2:
                raise OSError("synthetic shard write failure")
        if path == output and failure in {"entry", "inline_entry"}:
            raise OSError("synthetic entry write failure")
        return real_write(path, text, **kwargs)

    monkeypatch.setattr(generator, "atomic_write_text", fail_write)
    pairs = (
        [("New", "Replacement")]
        if failure == "inline_entry"
        else [(f"New field {index}: [value]", f"New value {index}: [value]") for index in range(4)]
    )
    with pytest.raises(OSError, match="synthetic"):
        generator.write_replace_script(output, pairs)

    assert output.read_bytes() == previous_script
    assert output.with_suffix(".rpyc").read_bytes() == b"previous compiled hook"
    assert all(path.read_bytes() == payload for path, payload in previous_data.items())
    assert dict(generator.read_generated_replace_pairs(output, {pair[0] for pair in old_pairs})) == dict(old_pairs)
    assert _run_hook(output, "Old field 3: 27") == "Old value 3: 27"


@pytest.mark.parametrize("inline", [False, True])
def test_successful_hook_update_cleans_previous_shards_after_switch(previous_hook, monkeypatch, inline):
    output, _old_pairs = previous_hook
    data_dir = output.parent / generator.REPLACE_DATA_DIR
    previous_files = set(data_dir.glob("*.json"))
    unrelated = data_dir / "user-notes.json"
    unrelated.write_bytes(b"retained")
    real_write = generator.atomic_write_text

    def observe_switch(path, text, **kwargs):
        if Path(path) == output:
            assert all(shard.is_file() for shard in previous_files)
            assert _run_hook(output, "Old field 3: 27") == "Old value 3: 27"
        return real_write(path, text, **kwargs)

    monkeypatch.setattr(generator, "atomic_write_text", observe_switch)
    pairs = (
        [("New", "Replacement")]
        if inline
        else [(f"New field {index}: [value]", f"New value {index}: [value]") for index in range(4)]
    )
    generator.write_replace_script(output, pairs)

    assert not output.with_suffix(".rpyc").exists()
    assert not any(path.exists() for path in previous_files)
    assert unrelated.read_bytes() == b"retained"
    assert dict(generator.read_generated_replace_pairs(output, {pair[0] for pair in pairs})) == dict(pairs)
    if inline:
        assert list(data_dir.glob("*.json")) == [unrelated]
        assert _run_hook(output, "New") == "Replacement"
    else:
        assert len(list(data_dir.glob("*.json"))) > 1
        assert _run_hook(output, "New field 3: 27") == "New value 3: 27"


def test_empty_hook_removes_generated_shards_after_entries(previous_hook, monkeypatch):
    output, _old_pairs = previous_hook
    data_dir = output.parent / generator.REPLACE_DATA_DIR
    generated_files = set(data_dir.glob("*.json"))
    unrelated = data_dir / "user-notes.json"
    unrelated.write_bytes(b"retained")
    real_unlink = Path.unlink

    def observe_unlink(path, *args, **kwargs):
        if path in generated_files:
            assert not output.exists()
            assert not output.with_suffix(".rpyc").exists()
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", observe_unlink)
    result = generator.generate_replace_from_miss(output.parent.parent.parent, "chinese")

    assert result == (None, 0)
    assert not output.exists()
    assert not output.with_suffix(".rpyc").exists()
    assert list(data_dir.glob("*.json")) == [unrelated]
    assert unrelated.read_bytes() == b"retained"


@pytest.mark.parametrize("failed_suffix", [".rpy", ".rpyc"])
def test_empty_hook_keeps_shards_when_entry_removal_fails(previous_hook, monkeypatch, failed_suffix):
    output, _old_pairs = previous_hook
    data_dir = output.parent / generator.REPLACE_DATA_DIR
    previous_data = {path: path.read_bytes() for path in data_dir.glob("*.json")}
    real_unlink = Path.unlink

    def fail_unlink(path, *args, **kwargs):
        if path == output.with_suffix(failed_suffix):
            raise OSError("synthetic entry removal failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(OSError, match="synthetic"):
        generator.generate_replace_from_miss(output.parent.parent.parent, "chinese")

    assert output.with_suffix(failed_suffix).exists()
    assert all(path.read_bytes() == payload for path, payload in previous_data.items())
