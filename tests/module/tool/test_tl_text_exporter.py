"""TlTextExporter：导出/回填边界（临时目录，不触真实游戏）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from module.Extract.TlTextExporter import (
    TlTextExporterError,
    apply_translations_to_tl,
    extract_pending_from_tl,
)


def _write_tl(tl_dir: Path, relative: str, body: str) -> Path:
    path = tl_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _sample_rpy(old: str = "Hello", new: str = "") -> str:
    return (
        "translate chinese strings:\n"
        f'    old "{old}"\n'
        f'    new "{new}"\n'
    )


def test_extract_and_apply_roundtrip(tmp_path: Path) -> None:
    project = tmp_path / "Demo"
    tl = project / "game" / "tl" / "chinese"
    _write_tl(tl, "script.rpy", _sample_rpy("Hello", ""))
    _write_tl(tl, "sub/more.rpy", _sample_rpy("World", "World"))  # pending: new==old
    txt = tmp_path / "pending.txt"
    count, manifest = extract_pending_from_tl(tl, txt)
    assert count == 2
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    assert doc["tl_root"]
    assert Path(doc["tl_root"]).resolve() == tl.resolve()
    assert len(doc["entries"]) == 2

    translated = tmp_path / "done.txt"
    translated.write_text("你好\n世界\n", encoding="utf-8")
    out = project / "game" / "tl" / "chinese_translated"
    filled, out_dir = apply_translations_to_tl(manifest, translated, out)
    assert filled == 2
    assert out_dir == out.resolve()
    assert "你好" in (out / "script.rpy").read_text(encoding="utf-8")
    assert "世界" in (out / "sub" / "more.rpy").read_text(encoding="utf-8")
    # 源 TL 不变
    assert 'new ""' in (tl / "script.rpy").read_text(encoding="utf-8")


def test_apply_rejects_short_txt_without_write(tmp_path: Path) -> None:
    project = tmp_path / "Demo"
    tl = project / "game" / "tl" / "chinese"
    _write_tl(tl, "script.rpy", _sample_rpy())
    txt = tmp_path / "pending.txt"
    _, manifest = extract_pending_from_tl(tl, txt)
    out = project / "game" / "tl" / "chinese_translated"
    out.mkdir(parents=True)
    marker = out / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(TlTextExporterError, match="少于"):
        apply_translations_to_tl(manifest, empty, out, confirm_overwrite=True)
    # 两条条目但只一行
    short = tmp_path / "short.txt"
    short.write_text("only-one\n", encoding="utf-8")
    _write_tl(tl, "b.rpy", _sample_rpy("Second", ""))
    _, manifest = extract_pending_from_tl(tl, txt)
    with pytest.raises(TlTextExporterError, match="少于"):
        apply_translations_to_tl(manifest, short, out, confirm_overwrite=True)
    assert marker.read_text(encoding="utf-8") == "keep"


def test_apply_stale_manifest_and_forge_file(tmp_path: Path) -> None:
    project = tmp_path / "Demo"
    tl = project / "game" / "tl" / "chinese"
    rpy = _write_tl(tl, "script.rpy", _sample_rpy("Hello", ""))
    txt = tmp_path / "pending.txt"
    _, manifest = extract_pending_from_tl(tl, txt)
    # 伪造绝对路径文件
    forged = tmp_path / "evil.rpy"
    forged.write_text(_sample_rpy("x", ""), encoding="utf-8")
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["entries"][0]["file"] = str(forged)
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    translated = tmp_path / "done.txt"
    translated.write_text("嗨\n", encoding="utf-8")
    with pytest.raises(TlTextExporterError, match="不在源 TL"):
        apply_translations_to_tl(manifest, translated, project / "game" / "tl" / "out")

    # 陈旧 old
    _, manifest = extract_pending_from_tl(tl, txt)
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["entries"][0]["old"] = "changed"
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TlTextExporterError, match="不匹配"):
        apply_translations_to_tl(manifest, translated, project / "game" / "tl" / "out2")
    assert rpy.read_text(encoding="utf-8").count("Hello") == 1


def test_apply_keeps_old_output_on_overlap_reject(tmp_path: Path) -> None:
    project = tmp_path / "Demo"
    tl = project / "game" / "tl" / "chinese"
    _write_tl(tl, "script.rpy", _sample_rpy())
    txt = tmp_path / "pending.txt"
    _, manifest = extract_pending_from_tl(tl, txt)
    translated = tmp_path / "done.txt"
    translated.write_text("你好\n", encoding="utf-8")
    with pytest.raises(TlTextExporterError, match="重叠|相同"):
        apply_translations_to_tl(manifest, translated, tl)


def test_apply_overwrite_requires_confirm_and_preserves_on_fail(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "Demo"
    tl = project / "game" / "tl" / "chinese"
    _write_tl(tl, "script.rpy", _sample_rpy())
    txt = tmp_path / "pending.txt"
    _, manifest = extract_pending_from_tl(tl, txt)
    translated = tmp_path / "done.txt"
    translated.write_text("你好\n", encoding="utf-8")
    out = project / "game" / "tl" / "chinese_translated"
    out.mkdir(parents=True)
    keep = out / "old.txt"
    keep.write_text("old-output", encoding="utf-8")
    with pytest.raises(TlTextExporterError, match="确认覆盖"):
        apply_translations_to_tl(manifest, translated, out)
    assert keep.read_text(encoding="utf-8") == "old-output"

    # 成功覆盖
    filled, _ = apply_translations_to_tl(manifest, translated, out, confirm_overwrite=True)
    assert filled == 1
    assert not keep.exists()
    assert (out / "script.rpy").is_file()


def test_legacy_list_manifest_needs_safe_root(tmp_path: Path) -> None:
    project = tmp_path / "Demo"
    tl = project / "game" / "tl" / "chinese"
    rpy = _write_tl(tl, "script.rpy", _sample_rpy())
    # 旧 list 清单
    manifest = tmp_path / "old.manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "seq": 0,
                    "file": str(rpy.resolve()),
                    "new_line_index": 2,
                    "old": "Hello",
                }
            ]
        ),
        encoding="utf-8",
    )
    translated = tmp_path / "done.txt"
    translated.write_text("你好\n", encoding="utf-8")
    out = project / "game" / "tl" / "chinese_translated"
    filled, _ = apply_translations_to_tl(
        manifest,
        translated,
        out,
        source_tl_dir=tl,
    )
    assert filled == 1


def test_extract_rejects_real_newline_in_old(tmp_path: Path) -> None:
    tl = tmp_path / "game" / "tl" / "chinese"
    # 直接写入含换行的字面量（转义形式），解码后含真实换行
    body = (
        "translate chinese strings:\n"
        '    old "line1\\nline2"\n'
        '    new ""\n'
    )
    _write_tl(tl, "script.rpy", body)
    with pytest.raises(TlTextExporterError, match="换行"):
        extract_pending_from_tl(tl, tmp_path / "out.txt")


def test_empty_translation_not_counted(tmp_path: Path) -> None:
    project = tmp_path / "Demo"
    tl = project / "game" / "tl" / "chinese"
    _write_tl(tl, "script.rpy", _sample_rpy("Hello", ""))
    txt = tmp_path / "pending.txt"
    _, manifest = extract_pending_from_tl(tl, txt)
    translated = tmp_path / "done.txt"
    translated.write_text("\n", encoding="utf-8")  # 空译文
    out = project / "game" / "tl" / "out"
    filled, _ = apply_translations_to_tl(manifest, translated, out)
    assert filled == 0
    assert 'new ""' in (out / "script.rpy").read_text(encoding="utf-8")


def test_apply_rejects_duplicate_and_missing_seq(tmp_path: Path) -> None:
    project = tmp_path / "Demo"
    tl = project / "game" / "tl" / "chinese"
    _write_tl(tl, "script.rpy", _sample_rpy("Hello", ""))
    _write_tl(tl, "b.rpy", _sample_rpy("World", ""))
    txt = tmp_path / "pending.txt"
    _, manifest = extract_pending_from_tl(tl, txt)
    translated = tmp_path / "done.txt"
    translated.write_text("你好\n世界\n", encoding="utf-8")
    out = project / "game" / "tl" / "out"

    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["entries"][1]["seq"] = 0  # 重复
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TlTextExporterError, match="重复"):
        apply_translations_to_tl(manifest, translated, out)

    _, manifest = extract_pending_from_tl(tl, txt)
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["entries"][1]["seq"] = 3  # 缺号 + 越界
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TlTextExporterError, match="缺号|连续"):
        apply_translations_to_tl(manifest, translated, out / "missing")


def test_apply_sorts_shuffled_seq_then_applies(tmp_path: Path) -> None:
    """乱序清单按 seq 排序后再应用，译文仍按序号对齐。"""
    project = tmp_path / "Demo"
    tl = project / "game" / "tl" / "chinese"
    _write_tl(tl, "script.rpy", _sample_rpy("Hello", ""))
    _write_tl(tl, "b.rpy", _sample_rpy("World", ""))
    txt = tmp_path / "pending.txt"
    _, manifest = extract_pending_from_tl(tl, txt)
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    assert [e["seq"] for e in doc["entries"]] == [0, 1]
    by_seq = {int(e["seq"]): e for e in doc["entries"]}
    doc["entries"] = list(reversed(doc["entries"]))
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    translated = tmp_path / "done.txt"
    translated.write_text("译0\n译1\n", encoding="utf-8")
    out = project / "game" / "tl" / "out_shuffled"
    filled, _ = apply_translations_to_tl(manifest, translated, out)
    assert filled == 2
    file0 = Path(by_seq[0]["file"]).name
    file1 = Path(by_seq[1]["file"]).name
    assert "译0" in (out / file0).read_text(encoding="utf-8")
    assert "译1" in (out / file1).read_text(encoding="utf-8")


def test_apply_rejects_extra_translation_lines(tmp_path: Path) -> None:
    project = tmp_path / "Demo"
    tl = project / "game" / "tl" / "chinese"
    _write_tl(tl, "script.rpy", _sample_rpy("Hello", ""))
    txt = tmp_path / "pending.txt"
    _, manifest = extract_pending_from_tl(tl, txt)
    translated = tmp_path / "done.txt"
    translated.write_text("你好\n多余\n", encoding="utf-8")
    out = project / "game" / "tl" / "out_extra"
    with pytest.raises(TlTextExporterError, match="多于"):
        apply_translations_to_tl(manifest, translated, out)
    assert not out.exists()
