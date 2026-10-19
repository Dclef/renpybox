"""工作台世界观/角色卡的源码依据：声明标题、代表文本、跨场景样本、真实频次与可信触发词。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from module.Cache.CacheItem import CacheItem
from module.Workbench.AnalysisService import WorkbenchAnalysisService
from module.Workbench.CharacterScanner import CharacterCandidate, CharacterScanner


def make_item(src: str, file_path: str = "script.rpy", line_type: str = "DIALOGUE") -> CacheItem:
    item = CacheItem()
    item.set_src(src)
    item.set_file_path(file_path)
    item.set_extra_field({"renpy_source": {"line": 1, "line_type": line_type, "literal_slot": 0}})
    return item


def write_game(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "project"
    game = root / "game"
    game.mkdir(parents = True)
    for name, content in files.items():
        path = game / name
        path.parent.mkdir(parents = True, exist_ok = True)
        path.write_text(content, encoding = "utf-8")
    return root


def worldbook_response(project_name: str) -> str:
    return json.dumps(
        {
            "project_name": project_name,
            "genre": "奇幻",
            "setting_summary": "",
            "era_background": "",
            "tone_style": "",
            "narrative_rules": "",
            "format_rules": "",
            "spoiler_notes": "",
        },
        ensure_ascii = False,
    )


def run_worldbook(monkeypatch, root: Path | None, items=(), candidates=(), model_title: str = "Lovers"):
    prompts: list[str] = []

    def fake_request(self, config, platform, prompt, *, round_index=0, label="AI 分析"):
        prompts.append(prompt)
        return worldbook_response(model_title)

    monkeypatch.setattr(WorkbenchAnalysisService, "request_json_text", fake_request)
    monkeypatch.setattr(WorkbenchAnalysisService, "resolve_project_root", lambda self, config: root)
    draft, raw = WorkbenchAnalysisService().generate_worldbook_draft(
        config = SimpleNamespace(),
        platform = {},
        scope = "full",
        items = list(items),
        candidates = list(candidates),
    )
    return draft, raw, prompts[0]


# ---------------------------------------------------------------- 声明标题


def test_declared_title_overrides_hallucinated_project_name(tmp_path, monkeypatch):
    root = write_game(tmp_path, {
        "options.rpy": 'define config.name = _("Dark Magic")\ndefine build.name = "DarkMagic"\n',
        "script.rpy": 'label start:\n    "We watched movies/lovers/ together."\n',
    })

    draft, raw, prompt = run_worldbook(monkeypatch, root)

    assert draft["project_name"] == "Dark Magic"
    assert "Lovers" in raw  # 原始回复保持不变，便于排查
    assert "源码声明的游戏标题：Dark Magic" in prompt
    assert "build.name）：DarkMagic" in prompt


def test_declared_title_is_kept_literally_without_prettifying(tmp_path, monkeypatch):
    root = write_game(tmp_path, {
        "options.rpy": "define config.name = _('My_summer_job_Patreon')\ndefine build.name = \"mysummerjob\"\n",
    })

    draft, _, _ = run_worldbook(monkeypatch, root, model_title = "Dreamlands")

    assert draft["project_name"] == "My_summer_job_Patreon"


def test_dynamic_title_is_not_evaluated_and_falls_back_to_build_name(tmp_path, monkeypatch):
    root = write_game(tmp_path, {
        "options.rpy": (
            'define config.name = "Part" + suffix\n'
            'define build.name = "plainbuild"\n'
        ),
    })

    assert WorkbenchAnalysisService().read_declared_title(root) == {"build.name": "plainbuild"}
    draft, _, _ = run_worldbook(monkeypatch, root)
    assert draft["project_name"] == "plainbuild"


def test_interpolated_or_missing_title_discards_model_guess(tmp_path, monkeypatch):
    root = write_game(tmp_path, {
        "options.rpy": 'define config.name = _("[game_title]")\n',
        "screens.rpy": 'screen about():\n    text _("Join our Discord!")\n',
    })

    assert WorkbenchAnalysisService().read_declared_title(root) == {}
    draft, _, prompt = run_worldbook(monkeypatch, root)
    assert draft["project_name"] == ""
    assert "源码未声明游戏标题" in prompt


def test_title_found_in_other_top_level_script_when_options_lacks_it(tmp_path):
    root = write_game(tmp_path, {
        "options.rpy": "define config.version = \"1.0\"\n",
        "setup.rpy": "init python:\n    config.name = \"Night Shift\"  # 标题\n",
    })

    assert WorkbenchAnalysisService().read_declared_title(root) == {"config.name": "Night Shift"}


# ---------------------------------------------------------------- 代表文本


def test_representative_texts_prefer_story_over_ui_links_and_paths():
    service = WorkbenchAnalysisService()
    story = [make_item(f"Story line {index} in the village.", f"chapter{index % 3}.rpy") for index in range(30)]
    noise = [
        make_item("Previous logs {a=https://discord.gg/abc}Here{/a}", "screens.rpy", "NARRATION"),
        make_item("Takes a screenshot.", "screens.rpy", "NARRATION"),
        make_item("Back", "screens.rpy", "MENU_OPTION"),
        make_item("Text speed", "options.rpy", "NARRATION"),
        make_item("Outfit", "outfitgui.rpy", "NARRATION"),
        make_item("movies/lovers/", "bol.rpy", "CUSTOM"),
        make_item("???????", "characters.rpy"),
        make_item("Umar", "characters.rpy"),
    ]
    items = noise[:4] + story[:15] + noise[4:] + story[15:]

    selected = service.select_representative_texts(items, max_items = 10, exclude = ["Umar"])

    assert len(selected) == 10
    assert all(text.startswith("Story line") for text in selected)
    assert selected[0] == "Story line 0 in the village." and selected[-1] == "Story line 29 in the village."


def test_representative_texts_demote_bare_labels_and_headings():
    service = WorkbenchAnalysisService()
    items = [
        make_item("{b}Book of Lovers{/b}", "bol.rpy", "NARRATION"),
        make_item("news", "characters.rpy"),
        make_item("{size=200}{b}[config.version] SAVE{/b}{/size}", "script.rpy"),
        make_item("Welcome back, dear.", "script.rpy"),
        make_item("We should leave before dark!", "script.rpy"),
    ]

    selected = service.select_representative_texts(items, max_items = 2)

    assert selected == ["Welcome back, dear.", "We should leave before dark!"]


def test_representative_texts_fall_back_to_ui_only_when_story_is_short():
    service = WorkbenchAnalysisService()
    items = [
        make_item("Join us on https://discord.gg/xyz", "screens.rpy", "NARRATION"),
        make_item("Takes a screenshot.", "screens.rpy", "NARRATION"),
        make_item("Hello, traveler.", "script.rpy"),
        make_item("Choose your path", "script.rpy", "MENU_OPTION"),
    ]

    selected = service.select_representative_texts(items, max_items = 10)

    # 剧情 → 剧情里的其他文本 → 界面；链接文案始终剔除。
    assert selected == ["Hello, traveler.", "Choose your path", "Takes a screenshot."]


# ---------------------------------------------------------------- 角色样本与频次


def scene_project(tmp_path: Path, scenes: int = 10, lines_per_scene: int = 10) -> Path:
    files = {
        "characters.rpy": (
            'define a = Character("Alice")\n'
            'define b = Character("{b}Bob{/b}")\n'
            "define bobby = b\n"
        ),
    }
    for scene in range(scenes):
        body = [f"label scene_{scene:02d}:"]
        body += [f'    a "Scene {scene:02d} line {line:02d} from Alice."' for line in range(lines_per_scene)]
        body += [f'    bobby "Scene {scene:02d} reply {line:02d}."' for line in range(3)]
        files[f"scene_{scene:02d}.rpy"] = "\n".join(body) + "\n"
    return write_game(tmp_path, files)


def test_scanner_samples_cover_early_middle_and_late_scenes(tmp_path):
    CharacterScanner._CACHE.clear()
    root = scene_project(tmp_path)

    scan = CharacterScanner().scan_project(root)

    samples = scan.speaker_samples["Alice"]
    assert len(samples) == CharacterScanner.MAX_SAMPLES_PER_NAME
    scenes = {line.split()[1] for line in samples}
    assert {"00", "05", "09"} <= scenes
    assert scan.speaker_counts["Alice"] == 100
    # `define bobby = b` 的台词也算 Bob 的
    assert scan.speaker_counts["Bob"] == 30


def test_candidates_and_prompt_keep_cross_scene_source_exact_samples(tmp_path):
    CharacterScanner._CACHE.clear()
    root = scene_project(tmp_path)
    source_lines = {
        f"Scene {scene:02d} line {line:02d} from Alice." for scene in range(10) for line in range(10)
    }

    candidates = CharacterScanner().build_candidates(SimpleNamespace(glossary_data = []), [], root)
    alice = next(candidate for candidate in candidates if candidate.name == "Alice")

    assert len(alice.sample_lines) == CharacterScanner.CANDIDATE_SAMPLE_LIMIT
    assert set(alice.sample_lines) <= source_lines
    assert alice.sample_lines[0].startswith("Scene 00") and alice.sample_lines[-1].startswith("Scene 09")

    prompt = WorkbenchAnalysisService().build_character_prompt("full", [alice], {})
    prompt_samples = [line[2:] for line in prompt.splitlines() if line.startswith("- Scene ")]
    assert len(prompt_samples) == WorkbenchAnalysisService.CHARACTER_PROMPT_SAMPLES
    assert len({line.split()[1] for line in prompt_samples}) >= 6
    assert prompt_samples[-1].startswith("Scene 09")


def test_candidates_rank_by_real_speaker_counts_not_item_name_src(tmp_path):
    CharacterScanner._CACHE.clear()
    root = write_game(tmp_path, {
        "characters.rpy": 'define a = Character("Aaron")\ndefine z = Character("Zoe")\n',
        "script.rpy": "\n".join(
            ["label start:"]
            + [f'    a "Aaron says {index}."' for index in range(3)]
            + [f'    z "Zoe says {index}."' for index in range(40)]
        ),
    })
    # 源码模式条目没有 name_src；旧实现据此排序会得到全 0 → 字母序。
    items = [make_item(f"Zoe says {index}.") for index in range(40)]

    candidates = CharacterScanner().build_candidates(SimpleNamespace(glossary_data = []), items, root)

    assert [candidate.name for candidate in candidates] == ["Zoe", "Aaron"]
    assert candidates[0].sample_count == 40  # 真实台词数，而不是保留的样本条数
    assert len(candidates[0].sample_lines) == CharacterScanner.CANDIDATE_SAMPLE_LIMIT
    assert candidates[1].sample_count == 3


def test_worldbook_prompt_lists_top_characters_by_frequency(monkeypatch):
    candidates = [
        CharacterCandidate("Zoe", sample_count = 40),
        CharacterCandidate("Aaron", sample_count = 3),
    ]

    _, _, prompt = run_worldbook(monkeypatch, None, candidates = candidates)

    assert "- Zoe（源码台词 40 行）\n- Aaron（源码台词 3 行）" in prompt


def test_build_candidates_does_not_mutate_cached_scan(tmp_path):
    CharacterScanner._CACHE.clear()
    root = scene_project(tmp_path, scenes = 3)
    scanner = CharacterScanner()
    scan = scanner.scan_project(root)
    before = {key: list(value) for key, value in scan.speaker_samples.items()}

    first = scanner.build_candidates(SimpleNamespace(glossary_data = []), [], root)
    first[0].sample_lines.append("mutated")
    second = scanner.build_candidates(SimpleNamespace(glossary_data = []), [], root)

    assert scanner.scan_project(root) is scan
    assert scan.speaker_samples == before
    assert "mutated" not in second[0].sample_lines


# ---------------------------------------------------------------- 触发词


def contamination_project(tmp_path: Path) -> Path:
    return write_game(tmp_path, {
        "characters.rpy": (
            'define me = Character("{b}[persistent.my_name]{/b}")\n'
            'define gg = Character("[char_name]")\n'
            'define nami = Character("{b}Nami{/b}")\n'
            'define doctor = Character("{b}Hitomu{/b}")\n'
            'define ffairy = Character("{b}Flower Fairy{/b}")\n'
            'define dfairy = Character("{b}Dark Fairy{/b}")\n'
        ),
        "script.rpy": "\n".join([
            "label start:",
            '    doctor "Good morning, [me]. Have you seen [nami]?"',
            '    doctor "Your checkup is done, [char_name]."',
            '    nami "Thanks, [doctor]! I am Nami, by the way."',
            '    nami "[me], let us find the fairy in the forest."',
            '    ffairy "The fairy circle protects us."',
            '    dfairy "Dark magic is my domain."',
            '    "The fairy lights flicker over the lake."',
        ]),
    })


def test_scanner_attaches_only_own_character_variables(tmp_path):
    CharacterScanner._CACHE.clear()
    root = contamination_project(tmp_path)

    candidates = {
        candidate.name: candidate
        for candidate in CharacterScanner().build_candidates(SimpleNamespace(glossary_data = []), [], root)
    }

    assert candidates["Nami"].match_keywords == ["Nami", "[nami]"]
    assert candidates["Hitomu"].match_keywords == ["Hitomu", "[doctor]"]
    # 玩家变量不属于任何具名角色
    assert all("[me]" not in c.match_keywords and "[char_name]" not in c.match_keywords for c in candidates.values())


def test_model_keywords_cannot_contaminate_triggers(tmp_path):
    CharacterScanner._CACHE.clear()
    root = contamination_project(tmp_path)
    candidates = CharacterScanner().build_candidates(SimpleNamespace(glossary_data = []), [], root)
    by_name = {candidate.name: candidate for candidate in candidates}
    service = WorkbenchAnalysisService()
    identities = service._identity_names(candidates)
    parsed = [
        {
            "name": "Hitomu",
            "identity": "医生",
            "aliases": ["[me]", "Nami", "Doc", "hitomu"],
            "match_keywords": ["Hitomu", "checkup", "[me]", "[char_name]", "[nami]"],
        },
        {
            "name": "Flower Fairy",
            "identity": "妖精",
            "aliases": ["Fairy", "Flower", "ffairy", "Dark Fairy"],
            "match_keywords": ["Fairy", "forest"],
        },
    ]

    drafts = service.normalize_character_drafts_from_response(
        parsed,
        [by_name["Hitomu"], by_name["Flower Fairy"]],
        identities = identities,
    )
    cards = {card["name"]: card for card in drafts}

    assert cards["Hitomu"]["match_keywords"] == ["Hitomu", "[doctor]"]
    assert cards["Hitomu"]["aliases"] == []
    assert cards["Flower Fairy"]["match_keywords"] == ["Flower Fairy"]
    # "Fairy" 同时是 Dark Fairy 的身份，"Flower" 是可接受的整词简称；标识符和别的角色都被拒绝。
    assert cards["Flower Fairy"]["aliases"] == ["Flower"]


def test_trusted_aliases_and_grounded_full_names_are_preserved():
    service = WorkbenchAnalysisService()
    service._evidence_text = "Elena Carter runs the bar.\nThe lady thief struck again.\nValeria waved."
    elena = CharacterCandidate(
        "Elena",
        aliases = ["Ellie"],
        match_keywords = ["Elena", "[hel]"],
        sample_lines = ["Welcome to my bar."],
    )
    sakimi = CharacterCandidate("Lady Thief Sakimi", sample_lines = ["Catch me if you can!"])
    valerie = CharacterCandidate("Valerie", sample_lines = ["Hi there."])
    identities = service._identity_names([elena, sakimi, valerie])
    parsed = [
        {"name": "Elena", "identity": "老板", "aliases": ["Elena Carter", "Elena Smith", "Valerie"]},
        {"name": "Lady Thief Sakimi", "identity": "怪盗", "aliases": ["Sakimi", "Lady Thief", "Lady"]},
        {"name": "Valerie", "identity": "店员", "aliases": ["Valeria"], "match_keywords": ["Valeria", "[char_name]"]},
    ]

    cards = {
        card["name"]: card
        for card in service.normalize_character_drafts_from_response(parsed, [elena, sakimi, valerie], identities = identities)
    }

    assert cards["Elena"]["aliases"] == ["Ellie", "Elena Carter"]  # 源码里没有 Elena Smith
    assert cards["Elena"]["match_keywords"] == ["Elena", "Ellie", "[hel]"]
    # lady/thief 在语料里多为小写普通词，"Lady Thief" 不能单独当触发词
    assert cards["Lady Thief Sakimi"]["aliases"] == ["Sakimi"]
    # 拼写变体不能被猜成同一人
    assert cards["Valerie"]["aliases"] == []
    assert cards["Valerie"]["match_keywords"] == ["Valerie"]


def test_name_part_alias_is_not_generic_just_because_variable_is_lowercase():
    service = WorkbenchAnalysisService()
    service._evidence_text = service._build_evidence(
        ["Where is [sakimi]?", "[sakimi] stole it.", "[sakimi]!", "Sakimi laughed.", "The yellow eye is watching."]
    )
    sakimi = CharacterCandidate("Lady Thief Sakimi", match_keywords = ["Lady Thief Sakimi", "[sakimi]"])
    eye = CharacterCandidate("The Yellow Eye")
    parsed = [
        {"name": "Lady Thief Sakimi", "identity": "怪盗", "aliases": ["Sakimi"]},
        {"name": "The Yellow Eye", "identity": "存在", "aliases": ["Yellow Eye"]},
    ]

    cards = {card["name"]: card for card in service.normalize_character_drafts_from_response(parsed, [sakimi, eye])}

    assert cards["Lady Thief Sakimi"]["aliases"] == ["Sakimi"]
    assert cards["The Yellow Eye"]["aliases"] == []  # 语料里是小写普通词组


def test_character_prompt_marks_cooccurrence_and_counts_as_weak_evidence():
    candidate = CharacterCandidate(
        "Rick",
        match_keywords = ["Rick", "[rik]"],
        sample_lines = ["Hey."],
        related_names = ["Elena", "Valerie"],
        sample_count = 57,
    )

    prompt = WorkbenchAnalysisService().build_character_prompt("full", [candidate], {})

    assert "源码可确认的称呼: Rick, [rik]" in prompt
    assert "同文件出现的其他说话人: Elena, Valerie" in prompt
    assert "源码台词行数: 57" in prompt
    assert "不代表已确立的关系" in prompt
    assert "不是总出场次数" in prompt and "只出现一次" in prompt
    assert "可能/疑似" in prompt
