from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Extract.ReplaceGenerator import (
    build_old_new_replace_plan,
    collect_translated_old_new_pairs,
    generate_replace_from_miss,
    read_generated_replace_pairs,
)
from module.File.RENPYHOOK import RENPYHOOK
from module.Config import Config


def test_miss_rpy_unescapes_literal_backslash_n_without_corrupting_text(tmp_path) -> None:
    """miss.rpy 里的字面 ``\\n`` 必须还原成两字符，不能变成真换行。

    写入侧 escape_string 先把 ``\\`` 写成 ``\\\\`` 再把换行写成 ``\\n``；读取侧
    旧实现顺序写反（先 ``\\n`` 后 ``\\\\``），原文里的字面反斜杠+n 会被解成真
    换行，该 replace 规则就永久匹配不上游戏文本、hook 静默失效、游戏里退回英文。
    """
    game = tmp_path / "game"
    tl_dir = game / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    miss = tl_dir / "miss" / "miss_ready_replace.rpy"
    miss.parent.mkdir()
    # 规则原文/译文里都含字面 `\n`（两字符，非换行）与一个真实转义换行。
    miss.write_text(
        'translate chinese strings:\n\n'
        '    old "Path C:\\\\new\\\\file"\n'
        '    new "路径 C:\\\\new\\\\file 译名"\n\n'
        '    old "Line one\\\\nline two"\n'
        '    new "第一行\\\\n第二行"\n',
        encoding="utf-8",
    )

    pairs = dict(build_old_new_replace_plan(game, "chinese").pairs)

    assert pairs["Path C:\\new\\file"] == "路径 C:\\new\\file 译名"
    assert pairs["Line one\\nline two"] == "第一行\\n第二行"


def test_old_new_replace_plan_keeps_runtime_suffix_and_uses_longest_first(tmp_path) -> None:
    game = tmp_path / "game"
    tl_dir = game / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    old "Native"\n'
        '    new "原生"\n\n'
        '    # renpybox: replace-only\n'
        '    old "Open"\n'
        '    new "打开"\n\n'
        '    # renpybox: replace-only\n'
        '    old "Open Door"\n'
        '    new "打开门"\n',
        encoding="utf-8",
    )
    miss = tl_dir / "miss" / "miss_ready_replace.rpy"
    miss.parent.mkdir()
    miss.write_text(
        'translate chinese strings:\n\n'
        '    old "Guide"\n'
        '    new "攻略"\n',
        encoding="utf-8",
    )

    plan = build_old_new_replace_plan(game, "chinese")

    assert plan.old_new_count == 2
    assert plan.supplement_count == 1
    assert [original for original, _ in plan.pairs] == ["Open Door", "Guide", "Open"]
    rendered = "Open Door{color=#ff6699}Guide{/color}"
    for original, translation in plan.pairs:
        rendered = rendered.replace(original, translation)
    assert rendered == "打开门{color=#ff6699}攻略{/color}"

    stale_rpyc = tl_dir / "replace_text_auto.rpyc"
    stale_rpyc.write_bytes(b"stale")
    output_path, count = generate_replace_from_miss(game, "chinese")
    assert output_path == tl_dir / "replace_text_auto.rpy"
    assert count == 3
    assert not stale_rpyc.exists()
    script = output_path.read_text(encoding="utf-8")
    assert '.replace("Native", "原生")' not in script
    assert read_generated_replace_pairs(output_path, {"Open Door", "Open", "Guide"}) == list(plan.pairs)


def test_old_new_replace_skips_conflicts_and_non_active_work_files(tmp_path) -> None:
    tl_dir = tmp_path / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("a.rpy").write_text(
        'translate chinese strings:\n\n'
        '    old "Same"\n'
        '    new "甲"\n\n'
        '    old "Stable"\n'
        '    new "稳定"\n',
        encoding="utf-8",
    )
    tl_dir.joinpath("b.rpy").write_text(
        'translate chinese strings:\n\n'
        '    old "Same"\n'
        '    new "乙"\n',
        encoding="utf-8",
    )
    work = tl_dir / "miss" / "miss_ready_replace.rpy"
    work.parent.mkdir()
    work.write_text(
        'translate chinese strings:\n\n'
        '    old "Work only"\n'
        '    new "中间文件"\n',
        encoding="utf-8",
    )

    pairs, conflicts = collect_translated_old_new_pairs(tl_dir)

    assert pairs == [("Stable", "稳定")]
    assert conflicts == 1


def test_collect_translated_old_new_pairs_can_filter_by_language(tmp_path) -> None:
    """多语言共用一个扫描目录时，必须能只取一种语言的 old/new。

    钩子渲染成 ``translate <language> python:`` 块，只在该语言目录里生效。
    旧实现不按语言过滤，于是同一原文在中文是"甲"、日文是"乙"就被当成
    "同一原文多译文"整条丢弃（conflicts+1，mapping 里被 pop），钩子因此永远
    生成不出来——多语言项目反复写回都看不到任何效果，也不报错。
    """
    tl_dir = tmp_path / "game" / "tl"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("multilang.rpy").write_text(
        'translate chinese strings:\n\n'
        '    old "Fictional helm"\n'
        '    new "甲"\n\n'
        'translate japanese strings:\n\n'
        '    old "Fictional helm"\n'
        '    new "乙"\n',
        encoding="utf-8",
    )

    # 不传 language 时保持旧行为：整条丢弃并计一次冲突。
    assert collect_translated_old_new_pairs(tl_dir) == ([], 1)

    assert collect_translated_old_new_pairs(tl_dir, language="chinese") == (
        [("Fictional helm", "甲")],
        0,
    )
    assert collect_translated_old_new_pairs(tl_dir, language="japanese") == (
        [("Fictional helm", "乙")],
        0,
    )
    # 大小写与首尾空白不能让过滤失效（钩子的 tl_name 可能来自用户输入）。
    assert collect_translated_old_new_pairs(tl_dir, language="  Japanese ") == (
        [("Fictional helm", "乙")],
        0,
    )
    assert collect_translated_old_new_pairs(tl_dir, language="korean") == ([], 0)


def test_replace_only_marker_does_not_leak_past_commented_duplicate(tmp_path) -> None:
    game = tmp_path / "game"
    tl_dir = game / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    # renpybox: replace-only\n'
        '    # [renpybox] duplicate; first at strings.rpy:4\n'
        '    # old "Duplicate"\n'
        '    # new "重复"\n\n'
        '    old "Native"\n'
        '    new "原生"\n',
        encoding="utf-8",
    )

    plan = build_old_new_replace_plan(game, "chinese")

    assert plan.pairs == ()


def test_generate_replace_removes_stale_hook_when_no_pairs_remain(tmp_path) -> None:
    game = tmp_path / "game"
    tl_dir = game / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    hook = tl_dir / "replace_text_auto.rpy"
    hook.write_text("stale", encoding="utf-8")
    hook.with_suffix(".rpyc").write_bytes(b"stale")

    output_path, count = generate_replace_from_miss(game, "chinese")

    assert output_path is None
    assert count == 0
    assert not hook.exists()
    assert not hook.with_suffix(".rpyc").exists()


def test_generate_replace_keeps_hook_when_tl_dir_cannot_be_read(tmp_path) -> None:
    """译文目录读不到时**不能**删钩子。

    ``generate_replace_from_miss`` 的译文来源目录（``tl_dir``）与钩子落盘目录
    （``output_dir``）是两个参数：多语言项目里多个语言共用一个来源目录，但各自
    把钩子写进自己的 ``tl/<lang>/``。来源目录一旦读不到（被移动/改名/权限不足），
    计划一定是空的——但这跟"用户把带标记的译文删光了"是完全不同的两件事。

    旧实现不区分二者，一律 unlink：玩家游戏里正在生效的运行时兜底译文会全部
    退回原文，而 ``replace_text`` 没有兜底重新启用。
    """
    game = tmp_path / "game"
    tl_dir = game / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    hook = tl_dir / "replace_text_auto.rpy"
    # 先写出一个真实可用的钩子（含诊断报告，记录 rule_count）。
    from module.Extract.ReplaceGenerator import write_replace_script

    write_replace_script(hook, [("Supplied line", "补漏译文")])
    hook.with_suffix(".rpyc").write_bytes(b"stale")
    before = hook.read_bytes()

    # 译文来源目录被移走/改名，钩子落盘目录仍在原处。
    moved_away = game / "tl" / "chinese_old"
    output_path, count = generate_replace_from_miss(
        game, "chinese", tl_dir=moved_away, output_dir=tl_dir
    )

    assert output_path == hook
    assert count == 1
    assert hook.exists()
    assert hook.read_bytes() == before
    assert hook.with_suffix(".rpyc").exists()


def test_generate_replace_keeps_hook_when_every_pair_conflicts(tmp_path) -> None:
    """同原文多译文被整条丢弃时，钩子不能跟着空计划一起消失。"""
    game = tmp_path / "game"
    tl_dir = game / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    hook = tl_dir / "replace_text_auto.rpy"
    from module.Extract.ReplaceGenerator import write_replace_script

    write_replace_script(hook, [("Supplied line", "补漏译文")])
    before = hook.read_bytes()

    # 同一原文在两个文件里各有各的译文 → 两条都被冲突规则丢弃。
    for name, translation in (("a.rpy", "译一"), ("b.rpy", "译二")):
        tl_dir.joinpath(name).write_text(
            'translate chinese strings:\n\n'
            '    # renpybox: replace-only\n'
            f'    old "Contested line"\n'
            f'    new "{translation}"\n',
            encoding="utf-8",
        )

    output_path, count = generate_replace_from_miss(game, "chinese")

    assert output_path == hook
    assert count == 0
    assert hook.exists()
    assert hook.read_bytes() == before


def test_hook_write_combines_marked_old_new_with_supplement_items(tmp_path) -> None:
    root = tmp_path / "MyGame"
    tl_dir = root / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    old "Native"\n'
        '    new "原生"\n\n'
        '    # renpybox: replace-only\n'
        '    old "Choice"\n'
        '    new "选项"\n',
        encoding="utf-8",
    )
    config = Config()
    config.renpy_project_path = str(root)
    config.renpy_game_folder = str(root)
    config.renpy_tl_folder = str(tl_dir)
    config.output_folder = str(root / "RenpyBox_Translation" / "chinese")
    item = CacheItem.from_dict(
        {
            "src": "Guide",
            "dst": "攻略",
            "row": 1,
            "file_type": CacheItem.FileType.RENPYHOOK,
            "text_type": CacheItem.TextType.RENPY,
            "status": Base.TranslationStatus.TRANSLATED,
        }
    )

    RENPYHOOK(config).write_to_path([item])

    script = (tl_dir / "replace_text_auto.rpy").read_text(encoding="utf-8")
    assert '.replace("Native", "原生")' not in script
    assert dict(read_generated_replace_pairs(tl_dir / "replace_text_auto.rpy", {"Choice", "Guide"})) == {"Choice": "选项", "Guide": "攻略"}


def test_hook_write_drops_supplement_entries_with_conflicting_translations(tmp_path) -> None:
    """同一原文被补漏条目翻成两个不同译文时，不能 last-wins 静默留一个。

    Hook 是纯全局子串替换，没有位置信息；保留后写入的译文会让结果随条目
    顺序漂移。正确行为是与 collect_translated_old_new_pairs 一致地整条丢弃，
    并显式告警（此前只在旧侧统计冲突，补漏侧的冲突完全无人知晓）。
    """
    root = tmp_path / "MyGame"
    tl_dir = root / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    config = Config()
    config.renpy_project_path = str(root)
    config.renpy_game_folder = str(root)
    config.renpy_tl_folder = str(tl_dir)
    config.output_folder = str(root / "RenpyBox_Translation" / "chinese")

    def hook_item(src: str, dst: str, row: int) -> CacheItem:
        return CacheItem.from_dict(
            {
                "src": src,
                "dst": dst,
                "row": row,
                "file_type": CacheItem.FileType.RENPYHOOK,
                "text_type": CacheItem.TextType.RENPY,
                "status": Base.TranslationStatus.TRANSLATED,
            }
        )

    items = [
        hook_item("Ambiguous", "甲", 1),
        hook_item("Ambiguous", "乙", 2),
        hook_item("Stable", "稳定", 3),
    ]

    RENPYHOOK(config).write_to_path(items)

    hook = tl_dir / "replace_text_auto.rpy"
    pairs = dict(read_generated_replace_pairs(hook, {"Ambiguous", "Stable"}))
    assert "Ambiguous" not in pairs
    assert pairs == {"Stable": "稳定"}


def test_generated_hook_pairs_are_read_for_marked_target_entries(tmp_path):
    """复用时自动钩子只恢复目标已标记的补漏条目。"""
    from module.Extract.ReplaceGenerator import read_generated_replace_pairs, write_replace_script
    hook = tmp_path / "replace_text_auto.rpy"
    write_replace_script(hook, [("Supplement", "补漏"), ("Official", "官方")])
    assert read_generated_replace_pairs(hook, {"Supplement"}) == [("Supplement", "补漏")]
