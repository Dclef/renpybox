import pytest

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Extract.ReplaceGenerator import read_generated_replace_pairs
from module.File.RENPY import RENPY
from module.File.RENPYSOURCE import RENPYSOURCE


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


def test_renpy_single_file_input_can_write_first_output(tmp_path):
    source = tmp_path / "fictional_single.rpy"
    original = (
        'translate chinese signal_11111111:\n'
        '    # guide "A fictional single-file signal."\n'
        '    guide "A fictional single-file signal."\n'
    )
    source.write_text(original, encoding="utf-8")
    config = Config()
    config.input_folder = str(source)
    config.output_folder = str(tmp_path / "output")
    writer = RENPY(config)
    items = writer.read_from_path([str(source)])
    assert len(items) == 1
    items[0].set_dst("虚构的单文件信号。")
    items[0].set_status(Base.TranslationStatus.TRANSLATED)

    writer.write_to_path(items)

    output = tmp_path / "output" / source.name
    assert "虚构的单文件信号。" in output.read_text(encoding="utf-8")
    assert source.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("writer_type", [RENPY, RENPYSOURCE])
@pytest.mark.parametrize("path_kind", ["relative", "absolute"])
def test_renpy_writers_reject_escape_before_backup(tmp_path, writer_type, path_kind):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    source = tmp_path / "fictional_victim.rpy"
    original = (
        'translate chinese signal_11111111:\n'
        '    # guide "The fictional sentinel."\n'
        '    guide "The fictional sentinel."\n'
        if writer_type is RENPY
        else 'guide "The fictional sentinel."\n'
    )
    source.write_text(original, encoding="utf-8")
    config = Config()
    config.input_folder = str(input_dir)
    config.output_folder = str(output_dir)
    config.renpy_backup_original = True
    writer = writer_type(config)
    items = writer.read_from_path([str(source)])
    assert len(items) == 1
    items[0].set_file_path(str(source) if path_kind == "absolute" else "../fictional_victim.rpy")
    items[0].set_dst("虚构的外部文件不得被覆盖。")
    items[0].set_status(Base.TranslationStatus.TRANSLATED)

    with pytest.raises(RuntimeError, match="escapes allowed roots"):
        writer.write_to_path(items)

    assert source.read_text(encoding="utf-8") == original
    assert not source.with_suffix(".rpy.bak").exists()
    assert not output_dir.exists()


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

def test_renpy_writeback_normalizes_values_before_unapplied_check(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source = input_dir / "fictional_ranger.rpy"
    input_dir.mkdir()
    source.write_text(
        'translate chinese ranger_demo_33333333:\n'
        '    # guide "The fictional ranger appears."\n'
        '    guide "The fictional ranger appears."\n',
        encoding="utf-8",
    )
    config = Config()
    config.input_folder = str(input_dir)
    config.output_folder = str(output_dir)
    writer = RENPY(config)

    expected = writer.read_from_path([str(source)])
    assert len(expected) == 1
    expected[0].set_dst("虚构的护林员出现了。")
    expected[0].set_name_dst(["虚构的护林员"])
    expected[0].set_status(Base.TranslationStatus.TRANSLATED)

    # 磁盘重解析结果：dst 带尾随空白、name_dst 为字符串而非列表。
    actual = writer.read_from_path([str(source)])
    actual[0].set_dst("虚构的护林员出现了。 ")
    actual[0].set_name_dst("虚构的护林员")

    unapplied = writer.find_unapplied_translations(expected, actual)
    assert unapplied == []


def test_renpy_writeback_regenerates_hook_for_every_marked_language(tmp_path):
    """同一文件里带 replace-only 标记的多种语言都要触发钩子重建。

    旧实现只在 ``len(hook_languages) == 1`` 时生成，多语言文件（Ren'Py 允许一个
    .rpy 里放多个 translate <lang> 块）会让钩子永远不更新，用户反复写回都看不到
    效果，而且没有任何报错或告警。

    钩子目录按语言分流。直接翻译页面把 input_folder 与 output_folder 都设成
    ``paths.tl_language_dir``（见 frontend/RenpyToolbox/DirectRpyTranslatePage.py），
    此时 output_folder 本身就是 ``tl/<lang>``，钩子留在原地，不能再套一层
    ``tl/<lang>/tl/<lang>/``；而整棵 ``tl/`` 一起写回时多个语言共用一个 output
    目录，必须各自写进自己的 ``tl/<lang>/``，否则后一种语言会覆盖前一种。
    本测试的 output_folder 是裸目录（既不在 tl 下，名字也不是语言名），落到
    ``output/tl/<lang>/`` 是唯一 Ren'Py 能找到的位置。
    """
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source = input_dir / "fictional_multilang.rpy"
    input_dir.mkdir()
    source.write_text(
        'translate chinese strings:\n\n'
        '    # renpybox: replace-only\n'
        '    old "Fictional helm"\n'
        '    new "虚构船舵"\n\n'
        'translate japanese strings:\n\n'
        '    # renpybox: replace-only\n'
        '    old "Fictional sail"\n'
        '    new "虚構の帆"\n',
        encoding="utf-8",
    )

    config = Config()
    config.input_folder = str(input_dir)
    config.output_folder = str(output_dir)
    writer = RENPY(config)
    items = writer.read_from_path([str(source)])
    assert len(items) == 2

    writer.write_to_path(items)

    # 钩子失效必须让调用方感知，所以这里能走到断言就说明没有静默跳过。
    # 一个钩子文件只渲染 translate <language> python: 块，只能承载一种语言，
    # 所以两种语言各自一个文件，而不是合在一起。
    chinese_hook = output_dir / "tl" / "chinese" / "replace_text_auto.rpy"
    japanese_hook = output_dir / "tl" / "japanese" / "replace_text_auto.rpy"
    assert chinese_hook.exists(), "chinese 钩子未生成"
    assert japanese_hook.exists(), "japanese 钩子未生成"
    # 按语言过滤只解决"冲突整条丢弃"，不能反过来让某个钩子混进别的语言，
    # 也不能让某一种语言的译文在游戏里永远不生效（曾被后一种语言整体覆盖）。
    assert dict(read_generated_replace_pairs(chinese_hook, {"Fictional helm", "Fictional sail"})) == {
        "Fictional helm": "虚构船舵",
    }
    assert dict(read_generated_replace_pairs(japanese_hook, {"Fictional helm", "Fictional sail"})) == {
        "Fictional sail": "虚構の帆",
    }


@pytest.mark.parametrize("with_ast", [True, False])
def test_renpy_writeback_validation_indexes_each_item_once(monkeypatch, with_ast):
    writer = RENPY(Config())
    items = [
        CacheItem(
            src=f"Fictional source {index}",
            dst=f"Fictional translation {index}",
            extra_field={
                "renpy": {
                    "block": {"lang": "chinese", "label": "strings"},
                    "digest": {"template_raw_sha1": str(index)},
                }
            } if with_ast else {},
        )
        for index in range(200)
    ]
    original = writer.build_ast_keys
    key_calls = 0

    def counted_keys(item):
        nonlocal key_calls
        key_calls += 1
        assert key_calls <= 2 * len(items)
        return original(item)

    monkeypatch.setattr(writer, "build_ast_keys", counted_keys)

    assert writer.find_unapplied_translations(items, list(reversed(items))) == []


def test_renpy_writeback_validation_prefers_exact_source_and_name():
    writer = RENPY(Config())
    shared_ast = {
        "renpy": {
            "block": {"lang": "chinese", "label": "strings"},
            "digest": {
                "template_raw_sha1": "raw",
                "template_raw_rstrip_sha1": "trimmed",
            },
        }
    }
    expected = CacheItem(src="Fictional signal", dst="Translated signal", name_src=["Guide"], extra_field=shared_ast)
    different_source = CacheItem(src="Other signal", dst="Wrong signal", name_src=["Guide"], extra_field=shared_ast)
    different_name = CacheItem(src=expected.src, dst="Wrong signal", name_src="Guide", extra_field=shared_ast)
    matching = CacheItem(src=expected.src, dst=expected.dst, name_src=expected.name_src, extra_field=shared_ast)

    assert writer.find_unapplied_translations([expected], [different_source, different_name, matching]) == []


def test_renpy_writeback_validation_does_not_reuse_ast_or_text_matches():
    writer = RENPY(Config())
    original = CacheItem(
        src="Fictional signal",
        dst="Translated signal",
        extra_field={
            "renpy": {
                "block": {"lang": "chinese", "label": "strings"},
                "digest": {
                    "template_raw_sha1": "raw",
                    "template_raw_rstrip_sha1": "trimmed",
                },
            }
        },
    )
    alias = CacheItem(src=original.src, dst=original.dst, extra_field={
        "renpy": {
            "block": {"lang": "chinese", "label": "strings"},
            "digest": {"template_raw_sha1": "trimmed"},
        }
    })
    text_only = CacheItem(src=original.src, dst=original.dst)

    assert writer.find_unapplied_translations([original, alias, text_only], [original]) == [alias, text_only]


def test_renpy_writeback_validation_keeps_ast_priority_over_text_fallback():
    writer = RENPY(Config())
    shared_ast = {
        "renpy": {
            "block": {"lang": "chinese", "label": "strings"},
            "digest": {"template_raw_sha1": "raw"},
        }
    }
    expected = CacheItem(src="Fictional signal", dst="Translated signal", extra_field=shared_ast)
    stale = CacheItem(src=expected.src, dst="Wrong signal", extra_field=shared_ast)
    text_only = CacheItem(src=expected.src, dst=expected.dst)

    assert writer.find_unapplied_translations([expected], [text_only, stale]) == [expected]
