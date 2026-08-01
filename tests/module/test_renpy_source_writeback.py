import json

import pytest

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.File.RENPYSOURCE import RENPYSOURCE


def test_source_writeback_accepts_already_applied_translation(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source = input_dir / "fictional_scene.rpy"
    output = output_dir / "fictional_scene.rpy"
    source.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    source.write_text('guide "A fictional aurora appears."\n', encoding="utf-8")
    output.write_text('guide "虚构的极光出现了。"\n', encoding="utf-8")

    config = Config()
    config.input_folder = str(input_dir)
    config.output_folder = str(output_dir)
    config.renpy_backup_original = False
    item = CacheItem(
        src="A fictional aurora appears.",
        dst="虚构的极光出现了。",
        row=1,
        file_path="fictional_scene.rpy",
        file_type=CacheItem.FileType.RENPYSOURCE,
        status=Base.TranslationStatus.TRANSLATED,
    )

    RENPYSOURCE(config).write_to_path([item])

    assert output.read_text(encoding="utf-8") == 'guide "虚构的极光出现了。"\n'
    report = json.loads(
        (output_dir / "writeback_report_renpy_source.json").read_text(
            encoding="utf-8"
        )
    )
    assert report[0]["applied"] == 0
    assert report[0]["already_applied"] == 1


def test_source_writeback_still_rejects_missing_source_and_destination(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source = input_dir / "fictional_scene.rpy"
    output = output_dir / "fictional_scene.rpy"
    source.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    source.write_text('guide "An old fictional signal."\n', encoding="utf-8")
    output.write_text('guide "An unrelated fictional signal."\n', encoding="utf-8")

    config = Config()
    config.input_folder = str(input_dir)
    config.output_folder = str(output_dir)
    config.renpy_backup_original = False
    item = CacheItem(
        src="An old fictional signal.",
        dst="一条旧的虚构信号。",
        row=1,
        file_path="fictional_scene.rpy",
        file_type=CacheItem.FileType.RENPYSOURCE,
        status=Base.TranslationStatus.TRANSLATED,
    )

    with pytest.raises(RuntimeError, match="译文未生效"):
        RENPYSOURCE(config).write_to_path([item])


def test_source_writeback_checks_destination_in_original_literal_slot(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source = input_dir / "fictional_screen.rpy"
    output = output_dir / "fictional_screen.rpy"
    source.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    source_line = (
        'textbutton "Launch the old fictional beacon" '
        'action Function(record_signal, "已翻译的虚构信标")\n'
    )
    output_line = (
        'textbutton "Launch fictional beacon" '
        'action Function(record_signal, "已翻译的虚构信标")\n'
    )
    source.write_text(source_line, encoding="utf-8")
    output.write_text(output_line, encoding="utf-8")

    config = Config()
    config.input_folder = str(input_dir)
    config.output_folder = str(output_dir)
    config.renpy_backup_original = False
    item = CacheItem(
        src="Launch the old fictional beacon",
        dst="已翻译的虚构信标",
        row=1,
        file_path="fictional_screen.rpy",
        file_type=CacheItem.FileType.RENPYSOURCE,
        status=Base.TranslationStatus.TRANSLATED,
    )

    with pytest.raises(RuntimeError, match="译文未生效"):
        RENPYSOURCE(config).write_to_path([item])

    assert output.read_text(encoding="utf-8") == output_line
