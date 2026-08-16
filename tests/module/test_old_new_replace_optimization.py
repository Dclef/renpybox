from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Extract.ReplaceGenerator import (
    build_old_new_replace_plan,
    collect_translated_old_new_pairs,
    generate_replace_from_miss,
)
from module.File.RENPYHOOK import RENPYHOOK
from module.Config import Config


def test_old_new_replace_plan_keeps_runtime_suffix_and_uses_longest_first(tmp_path) -> None:
    game = tmp_path / "game"
    tl_dir = game / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    old "Open"\n'
        '    new "打开"\n\n'
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

    output_path, count = generate_replace_from_miss(game, "chinese")
    assert output_path == tl_dir / "replace_text_auto.rpy"
    assert count == 3
    script = output_path.read_text(encoding="utf-8")
    assert script.index('.replace("Open Door", "打开门")') < script.index(
        '.replace("Open", "打开")'
    )


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


def test_hook_write_combines_standard_old_new_with_supplement_items(tmp_path) -> None:
    root = tmp_path / "MyGame"
    tl_dir = root / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
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
    assert '.replace("Choice", "选项")' in script
    assert '.replace("Guide", "攻略")' in script
