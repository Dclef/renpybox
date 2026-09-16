from types import SimpleNamespace

from module.Extract.ReplaceGenerator import render_replace_script


def _hook(pairs):
    namespace = {"config": SimpleNamespace(replace_text=None)}
    exec(render_replace_script(pairs).replace("translate chinese python:", "if True:"), namespace)
    return namespace["config"].replace_text


def test_static_replace_is_one_pass():
    hook = _hook([("Open Door", "Door"), ("Door", "Gate")])
    assert hook("Open Door") == "Door"


def test_precompiled_dynamic_rules_do_not_compile_on_calls(monkeypatch):
    hook = _hook([(f"Field{i}: [value]", f"Value{i}: [value]") for i in range(1000)])
    import re

    def fail_compile(*args, **kwargs):
        raise AssertionError("runtime regex compilation")

    monkeypatch.setattr(re, "compile", fail_compile)
    assert hook("unrelated text") == "unrelated text"
    assert hook("Field999: 27") == "Value999: 27"
