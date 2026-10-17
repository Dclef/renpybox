"""Agent 抽取与一键页一样：先配路径，再抽取，成功后落盘。"""

from pathlib import Path
from types import SimpleNamespace

from module.Agent.tools.pipeline_tools import run_project_extraction
from module.Config import Config


def _config(root: Path) -> Config:
    config = Config()
    config.platforms = []
    game = root / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config.renpy_project_path = str(root)
    config.renpy_game_folder = str(root)
    config.renpy_tl_folder = str(tl)
    config.input_folder = str(tl)
    config.output_folder = str(root / "old-out")
    config.target_language = "ZH"
    return config


def test_extraction_prepares_paths_and_uses_official_exe(tmp_path, monkeypatch) -> None:
    root = tmp_path / "Game"
    config = _config(root)
    exe = root / "Game.exe"
    exe.write_bytes(b"")
    order: list[str] = []
    saves: list[tuple[str, str, bool]] = []

    def save():
        saves.append((
            config.input_folder,
            config.output_folder,
            config.extract_use_custom,
        ))
        return config

    config.save = save

    def prepare(live, game_dir, tl_name, *, incremental):
        order.append(f"prepare:{incremental}")
        live.input_folder = str(root / "game" / "tl" / "chinese")
        live.output_folder = str(root / "RenpyBox_Translation" / "chinese")
        return {"output_dir": live.output_folder}

    def extract(*_args, **kwargs):
        order.append(f"extract:{kwargs.get('exe_path')}:{kwargs.get('incremental')}")
        return True, "ok", SimpleNamespace(
            success=True,
            tl_dir=root / "game" / "tl" / "chinese",
            incremental_dir=None,
            new_strings=2,
            cancelled=False,
        )

    monkeypatch.setattr(
        "module.Agent.tools.pipeline_tools.detect_game_status",
        lambda *_args, **_kwargs: ("ready", "ready"),
    )
    monkeypatch.setattr("module.Agent.tools.pipeline_tools.flow.prepare_extraction_paths", prepare)
    monkeypatch.setattr("module.Agent.tools.pipeline_tools.extract_project_text", extract)
    monkeypatch.setattr(
        "module.Tool.RenpyDecompiler.RenpyDecompiler._find_game_exe",
        lambda self, directory: exe,
    )

    result = run_project_extraction(
        config_loader=lambda: config,
        confirmed_project_root=str(root.resolve()),
        supplement_mode="off",
    )

    assert result.success is True
    assert order == [
        "prepare:False",
        f"extract:{exe}:False",
    ]
    assert saves[0][2] is False
    assert Path(saves[-1][1]) == root / "RenpyBox_Translation" / "chinese"
    assert config.output_folder == saves[-1][1]
    assert config.extract_supplement_mode == "off"


def test_extraction_keeps_supplement_setting_when_omitted(tmp_path, monkeypatch) -> None:
    root = tmp_path / "Game"
    config = _config(root)
    config.extract_supplement_mode = "aggressive"
    config.extract_use_custom = True

    monkeypatch.setattr(
        "module.Agent.tools.pipeline_tools.detect_game_status",
        lambda *_args, **_kwargs: ("ready", "ready"),
    )
    monkeypatch.setattr(
        "module.Agent.tools.pipeline_tools.flow.prepare_extraction_paths",
        lambda live, *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "module.Agent.tools.pipeline_tools.extract_project_text",
        lambda *_args, **_kwargs: (
            True,
            "ok",
            SimpleNamespace(
                success=True,
                cancelled=False,
                new_strings=1,
                tl_dir=root / "game" / "tl" / "chinese",
                incremental_dir=None,
            ),
        ),
    )
    monkeypatch.setattr(
        "module.Tool.RenpyDecompiler.RenpyDecompiler._find_game_exe",
        lambda self, directory: None,
    )

    result = run_project_extraction(
        config_loader=lambda: config,
        confirmed_project_root=str(root.resolve()),
    )

    assert result.success is True
    assert config.extract_supplement_mode == "aggressive"
    assert config.extract_use_custom is True


def test_extraction_rejects_exe_outside_project(tmp_path, monkeypatch) -> None:
    root = tmp_path / "Game"
    config = _config(root)
    called = {"extract": False}

    def extract(*_args, **_kwargs):
        called["extract"] = True
        return True, "ok", SimpleNamespace(success=True, cancelled=False, new_strings=0)

    monkeypatch.setattr(
        "module.Agent.tools.pipeline_tools.detect_game_status",
        lambda *_args, **_kwargs: ("ready", "ready"),
    )
    monkeypatch.setattr("module.Agent.tools.pipeline_tools.extract_project_text", extract)
    outside = tmp_path / "other.exe"
    outside.write_bytes(b"")

    result = run_project_extraction(
        config_loader=lambda: config,
        confirmed_project_root=str(root.resolve()),
        exe_path=str(outside),
    )

    assert result.code == "EXTRACTION_FAILED"
    assert called["extract"] is False
