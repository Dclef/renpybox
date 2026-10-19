"""模块级用例必须隔离配置与凭据，不能覆盖开发机正在使用的 config.json。

背景：``tests/api/conftest.py`` 的 ``isolated_api_config`` 只覆盖 ``tests/api``
目录。``tests/module`` 下的部分用例（例如 ``test_agent_extraction_parity`` 里
未 stub ``config.save`` 的那条）会走到 ``run_project_extraction`` 内部真实的
``Config.save()``；``Config.CONFIG_PATH`` 默认指向应用根目录的 ``config.json``，
于是 ``pytest`` 会把临时目录写进开发机的真实配置，下次启动 dev 时项目绑定
就被改成了 ``/tmp/pytest-.../Game``。

这里给整个 ``tests/module`` 目录兜底：默认把配置与日志重定向到**独立**临时目录。
必须用 ``tmp_path_factory`` 而不是 ``tmp_path``：若干用例把 ``tmp_path`` 当输入
目录并断言其中「只有自己写的文件」，共用目录会让 ``config.json`` 混进去。

显式覆盖（如 ``test_config_atomic_save`` 自己 monkeypatch ``CONFIG_PATH``）仍然
优先，因为 ``monkeypatch`` 在用例内后设置，撤销后回落到本 fixture 的值。
"""
import pytest

from base.LogManager import LogManager
from module.Config import Config
from module.Secret.SecretStore import MemoryBackend, SecretStore


@pytest.fixture(autouse=True)
def isolated_module_config(tmp_path_factory, monkeypatch):
    """把配置读写与日志落到独立临时目录，避免污染开发机真实文件。"""
    sandbox = tmp_path_factory.mktemp("module-config")
    monkeypatch.setattr(Config, "CONFIG_PATH", str(sandbox / "config.json"))
    monkeypatch.setattr(LogManager, "PATH", str(sandbox / "log"))
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))
    # 兜底基线：空路径 + 临时目录，和真实 config.json 的默认状态一致。
    config = Config()
    config.input_folder = str(sandbox / "input")
    config.output_folder = str(sandbox / "output")
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
    config.save(strict=True)
