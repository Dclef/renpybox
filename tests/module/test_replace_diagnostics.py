import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from module.Extract import ReplaceGenerator as generator


def _hook(pairs):
    namespace = {"config": SimpleNamespace(replace_text=None)}
    script = generator.render_replace_script(pairs)
    exec(script.replace("translate chinese python:", "if True:"), namespace)
    return namespace["config"].replace_text


def _read_report(output):
    return json.loads(output.with_suffix(generator.REPLACE_DIAGNOSTICS_SUFFIX).read_text(encoding="utf-8"))


def test_diagnostics_report_counts_risks_without_removing_rules(tmp_path):
    pairs = [
        ("Open Door", "Open the door"),
        ("[first][second]", "[second]|[first]"),
        ("Name: [name] / [name].", "[name] appears twice."),
        ("Score: [rank]", "Rank: [rank]"),
        ("Score: [tier]", "Tier: [tier]"),
        ("Score: [value] pts", "Points: [value]"),
        ("A [x]", "B [x]"),
    ]
    output = tmp_path / "replace_text_auto.rpy"
    generator.write_replace_script(output, pairs)
    report = _read_report(output)
    summary = report["summary"]

    assert summary["rule_count"] == len(pairs)
    assert summary["static_rule_count"] == 1
    assert summary["dynamic_rule_count"] == 6
    assert summary["no_anchor_rule_count"] == 1
    assert summary["multi_interpolation_rule_count"] == 2
    assert summary["shared_anchor_rule_count"] == 3
    assert summary["shared_anchor_group_count"] == 1
    assert summary["max_anchor_group_size"] == 3
    assert summary["ambiguous_pattern_group_count"] == 1
    assert summary["max_interpolations"] == 2
    assert summary["max_source_chars"] == max(len(source) for source, _target in pairs)
    assert summary["max_translation_chars"] == max(len(target) for _source, target in pairs)
    assert summary["script_bytes"] == output.stat().st_size
    assert summary["external_data_bytes"] == summary["external_data_file_count"] == 0
    assert summary["total_hook_bytes"] == summary["script_bytes"]
    assert report["meta"]["script_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert report["reason_counts"]["adjacent_interpolations"] == 1
    assert report["reason_counts"]["repeated_placeholder"] == 1
    assert report["reason_counts"]["short_anchor"] == 1
    assert report["reason_counts"]["ambiguous_pattern"] == 2
    assert dict(generator.read_generated_replace_pairs(output, {source for source, _ in pairs})) == dict(pairs)


def test_diagnostics_measures_external_shards_and_bounds_samples(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "REPLACE_SHARD_BYTES", 100)
    pairs = [(f"Shared [left{i}][right{i}]", f"Result [right{i}]/[left{i}]") for i in range(125)]
    output = tmp_path / "replace_text_auto.rpy"
    generator.write_replace_script(output, pairs)
    report = _read_report(output)
    summary = report["summary"]
    shards = list((output.parent / generator.REPLACE_DATA_DIR).glob("*.json"))

    assert summary["rule_count"] == summary["flagged_rule_count"] == 125
    assert summary["shared_anchor_rule_count"] == 125
    assert summary["sampled_rule_count"] == generator.REPLACE_DIAGNOSTICS_SAMPLE_LIMIT
    assert summary["omitted_rule_count"] == 25
    assert len(report["samples"]) == generator.REPLACE_DIAGNOSTICS_SAMPLE_LIMIT
    assert summary["external_data_bytes"] == sum(path.stat().st_size for path in shards)
    assert summary["external_data_bytes"] == summary["payload_bytes"]
    assert summary["external_data_file_count"] == len(shards)
    assert set(report["meta"]["external_data_files"]) == {path.name for path in shards}
    assert summary["total_hook_bytes"] == output.stat().st_size + summary["external_data_bytes"]
    assert len(generator.read_generated_replace_pairs(output, {source for source, _ in pairs})) == 125


def test_diagnostics_failure_does_not_fail_committed_hook(tmp_path, monkeypatch):
    output = tmp_path / "replace_text_auto.rpy"
    generator.write_replace_script(output, [("Old", "Previous")])
    report_path = output.with_suffix(generator.REPLACE_DIAGNOSTICS_SUFFIX)
    previous_report = report_path.read_bytes()
    real_write = generator.atomic_write_text

    def fail_report(path, text, **kwargs):
        if Path(path) == report_path:
            raise OSError("synthetic report failure")
        return real_write(path, text, **kwargs)

    monkeypatch.setattr(generator, "atomic_write_text", fail_report)
    assert generator.write_replace_script(output, [("New", "Current")]) == output
    assert generator.read_generated_replace_pairs(output, {"New"}) == [("New", "Current")]
    assert report_path.read_bytes() == previous_report
    assert _read_report(output)["meta"]["script_sha256"] != hashlib.sha256(output.read_bytes()).hexdigest()


def test_failed_entry_write_keeps_previous_diagnostics(tmp_path, monkeypatch):
    output = tmp_path / "replace_text_auto.rpy"
    generator.write_replace_script(output, [("Old", "Previous")])
    report_path = output.with_suffix(generator.REPLACE_DIAGNOSTICS_SUFFIX)
    previous_report = report_path.read_bytes()
    real_write = generator.atomic_write_text

    def fail_entry(path, text, **kwargs):
        if Path(path) == output:
            raise OSError("synthetic entry failure")
        return real_write(path, text, **kwargs)

    monkeypatch.setattr(generator, "atomic_write_text", fail_entry)
    with pytest.raises(OSError, match="synthetic entry"):
        generator.write_replace_script(output, [("New", "Current")])
    assert report_path.read_bytes() == previous_report
    assert _read_report(output)["meta"]["script_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


@pytest.mark.parametrize("fail_removal", [False, True])
def test_empty_rules_remove_report_only_after_hook_removal(tmp_path, monkeypatch, fail_removal):
    game = tmp_path / "game"
    output = game / "tl" / "chinese" / "replace_text_auto.rpy"
    generator.write_replace_script(output, [("Old", "Previous")])
    report_path = output.with_suffix(generator.REPLACE_DIAGNOSTICS_SUFFIX)
    real_unlink = Path.unlink

    def remove(path, *args, **kwargs):
        if path == output and fail_removal:
            raise OSError("synthetic removal failure")
        if path == report_path:
            assert not output.exists()
            assert not output.with_suffix(".rpyc").exists()
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", remove)
    if fail_removal:
        with pytest.raises(OSError, match="synthetic removal"):
            generator.generate_replace_from_miss(game, "chinese")
        assert report_path.exists()
    else:
        assert generator.generate_replace_from_miss(game, "chinese") == (None, 0)
        assert not report_path.exists()


def test_diagnostic_json_is_not_interpreted_as_translation_input(tmp_path):
    from module.Config import Config
    from module.File.KVJSON import KVJSON
    from module.File.MESSAGEJSON import MESSAGEJSON
    from module.File.RENpyTranslationsJSON import RENPYTRANSLATIONSJSON

    output = tmp_path / "replace_text_auto.rpy"
    generator.write_replace_script(output, [("Name: [name] / [name].", "Repeated [name].")])
    config = Config()
    config.input_folder = str(tmp_path)
    config.output_folder = str(tmp_path / "output")
    paths = [str(output.with_suffix(generator.REPLACE_DIAGNOSTICS_SUFFIX))]
    assert KVJSON(config).read_from_path(paths) == []
    assert MESSAGEJSON(config).read_from_path(paths) == []
    assert RENPYTRANSLATIONSJSON(config).read_from_path(paths) == []


def test_repeated_interpolation_requires_the_same_rendered_value():
    hook = _hook([("Name: [name] / [name].", "[name] appears twice.")])
    assert hook("Name: Alice / Alice.") == "Alice appears twice."
    assert hook("Name: Alice / Bob.") == "Name: Alice / Bob."


def test_multiple_interpolations_can_reorder_repeated_values():
    hook = _hook([("[name] gives [count] items to [name].", "[count] items: [name] -> [name].")])
    assert hook("Alice gives 3 items to Alice.") == "3 items: Alice -> Alice."
    assert hook("Alice gives 3 items to Bob.") == "Alice gives 3 items to Bob."


def test_shared_anchor_filters_complete_templates_without_cascading():
    hook = _hook([
        ("Score: [value] A", "First: [value]"),
        ("Score: [value] B", "Second: [value]"),
        ("Second: 27", "Cascaded"),
    ])
    assert hook("Score: 27 B") == "Second: 27"
    assert hook("Score: 27 A") == "First: 27"
    before = hook._renpybox_transform._renpybox_stats["dynamic_candidates"]
    assert hook("Score: 27 C") == "Score: 27 C"
    assert hook._renpybox_transform._renpybox_stats["dynamic_candidates"] - before == 2


def test_ambiguous_templates_keep_deterministic_priority():
    pairs = [("Score: [tier]", "Tier: [tier]"), ("Score: [rank]", "Rank: [rank]")]
    assert _hook(pairs)("Score: 9") == "Rank: 9"
    assert _hook(list(reversed(pairs)))("Score: 9") == "Rank: 9"


def test_adjacent_interpolations_remain_available_with_ambiguous_boundaries():
    hook = _hook([("[first][second]", "[second]|[first]")])
    assert hook("Alice") == "Alice|"
