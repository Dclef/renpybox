import ast
from collections import Counter
from pathlib import Path
from string import Formatter

from base.BaseLanguage import BaseLanguage
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Localizer.LocalizerEN import LocalizerEN
from module.Localizer.LocalizerZH import LocalizerZH


def _direct_string_resources(localizer: type) -> dict[str, str]:
    return {
        key: value
        for key, value in vars(localizer).items()
        if isinstance(value, str) and not key.startswith("__")
    }


def _format_fields(value: str) -> Counter:
    return Counter(
        (field_name, format_spec, conversion)
        for _, field_name, format_spec, conversion in Formatter().parse(value)
        if field_name is not None
    )


def _duplicate_class_attributes(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    names = [
        target.id
        for node in class_node.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (
            node.targets if isinstance(node, ast.Assign) else [node.target]
        )
        if isinstance(target, ast.Name)
    ]
    return {name for name in names if names.count(name) > 1}


def test_english_resources_explicitly_cover_every_chinese_resource() -> None:
    zh = _direct_string_resources(LocalizerZH)
    en = _direct_string_resources(LocalizerEN)

    assert en.keys() == zh.keys()


def test_localized_resources_keep_the_same_format_fields() -> None:
    zh = _direct_string_resources(LocalizerZH)
    en = _direct_string_resources(LocalizerEN)

    mismatches = {
        key: (_format_fields(zh[key]), _format_fields(en[key]))
        for key in zh.keys() & en.keys()
        if _format_fields(zh[key]) != _format_fields(en[key])
    }

    assert mismatches == {}


def test_localizer_classes_do_not_silently_override_resources() -> None:
    root = Path(__file__).parents[2]

    assert _duplicate_class_attributes(
        root / "module" / "Localizer" / "LocalizerZH.py", "LocalizerZH"
    ) == set()
    assert _duplicate_class_attributes(
        root / "module" / "Localizer" / "LocalizerEN.py", "LocalizerEN"
    ) == set()


def test_localizer_get_uses_the_selected_application_language() -> None:
    original = Localizer.get_app_language()
    try:
        Localizer.set_app_language(BaseLanguage.Enum.ZH)
        assert Localizer.get().error == "错误"
        assert Localizer.localize("中文", "English") == "中文"
        Localizer.set_app_language(BaseLanguage.Enum.EN)
        assert Localizer.get().error == "Error"
        assert Localizer.localize("中文", "English") == "English"
    finally:
        Localizer.set_app_language(original)


def test_application_language_round_trips_through_config(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = Config()
    config.app_language = BaseLanguage.Enum.EN
    config.save(str(path))

    loaded = Config().load(str(path))

    assert loaded.app_language == BaseLanguage.Enum.EN
    original = Localizer.get_app_language()
    try:
        Localizer.set_app_language(loaded.app_language)
        assert Localizer.get() is LocalizerEN
    finally:
        Localizer.set_app_language(original)
