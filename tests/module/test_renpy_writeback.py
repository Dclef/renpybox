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
