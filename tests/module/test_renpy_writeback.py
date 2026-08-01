import pytest

from base.Base import Base
from module.Config import Config
from module.File.RENPY import RENPY


def test_renpy_writeback_accepts_complete_translated_batch(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source = input_dir / "fictional_complete.rpy"
    input_dir.mkdir()
    source.write_text(
        'translate chinese signal_alpha_11111111:\n'
        '    # guide "The fictional amber signal appears."\n'
        '    guide "The fictional amber signal appears."\n\n'
        'translate chinese signal_beta_22222222:\n'
        '    # guide "The fictional violet signal appears."\n'
        '    guide "The fictional violet signal appears."\n',
        encoding="utf-8",
    )

    config = Config()
    config.input_folder = str(input_dir)
    config.output_folder = str(output_dir)
    writer = RENPY(config)
    items = writer.read_from_path([str(source)])
    assert len(items) == 2
    items[0].set_dst("虚构的琥珀信号出现了。")
    items[0].set_status(Base.TranslationStatus.TRANSLATED)
    items[1].set_dst("虚构的紫色信号出现了。")
    items[1].set_status(Base.TranslationStatus.TRANSLATED)

    writer.write_to_path(items)

    result = (output_dir / "fictional_complete.rpy").read_text(encoding="utf-8")
    assert "虚构的琥珀信号出现了。" in result
    assert "虚构的紫色信号出现了。" in result


def test_renpy_writeback_rejects_batch_when_stale_item_is_missing(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source = input_dir / "fictional_signals.rpy"
    target = output_dir / "fictional_signals.rpy"
    input_dir.mkdir()
    output_dir.mkdir()
    original = (
        'translate chinese signal_alpha_11111111:\n'
        '    # guide "The fictional amber signal appears."\n'
        '    guide "The fictional amber signal appears."\n\n'
        'translate chinese signal_beta_22222222:\n'
        '    # guide "The fictional violet signal appears."\n'
        '    guide "The fictional violet signal appears."\n'
    )
    source.write_text(original, encoding="utf-8")
    target.write_text(original, encoding="utf-8")

    config = Config()
    config.input_folder = str(input_dir)
    config.output_folder = str(output_dir)
    writer = RENPY(config)
    items = writer.read_from_path([str(source)])
    assert len(items) == 2
    items[0].set_dst("虚构的琥珀信号出现了。")
    items[0].set_status(Base.TranslationStatus.TRANSLATED)
    items[1].set_dst("虚构的紫色信号出现了。")
    items[1].set_status(Base.TranslationStatus.TRANSLATED)

    source.write_text(
        'translate chinese signal_alpha_11111111:\n'
        '    # guide "The fictional amber signal appears."\n'
        '    guide "The fictional amber signal appears."\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Ren'Py 写回未完整完成"):
        writer.write_to_path(items)

    assert target.read_text(encoding="utf-8") == original


def test_renpy_writeback_rejects_unapplied_name_only_translation(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source = input_dir / "fictional_name_only.rpy"
    input_dir.mkdir()
    source.write_text(
        'translate chinese beacon_name_33333333:\n'
        '    # Character("Captain Lumen") "The fictional beacon is steady."\n'
        '    Character("Captain Lumen") "The fictional beacon is steady."\n',
        encoding="utf-8",
    )

    config = Config()
    config.input_folder = str(input_dir)
    config.output_folder = str(output_dir)
    writer = RENPY(config)
    items = writer.read_from_path([str(source)])
    assert len(items) == 1
    assert items[0].get_name_src() == "Captain Lumen"
    items[0].set_name_dst("露明船长")

    # 模拟缓存生成后原文件角色名发生变化，使缓存中的 AST 身份失效。
    source.write_text(
        'translate chinese beacon_name_33333333:\n'
        '    # Character("Commander Vela") "The fictional beacon is steady."\n'
        '    Character("Commander Vela") "The fictional beacon is steady."\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="译文未完整写入"):
        writer.write_to_path(items)

    assert not (output_dir / "fictional_name_only.rpy").exists()
