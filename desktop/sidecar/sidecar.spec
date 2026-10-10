# -*- mode: python ; coding: utf-8 -*-
"""Self-contained API backend; deliberately excludes the legacy Qt application."""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

project_root = Path(SPECPATH).resolve().parents[1]
os.environ.setdefault("translators_default_region", "CN")

# The build driver prepares an allowlist from tracked resource files. Never copy
# the working tree's resource directory wholesale: it can contain API keys.
staging = project_root / "desktop" / "runtime" / "staging"
if not (staging / "resource" / "icon.ico").is_file():
    raise RuntimeError("Run npm run build:backend; packaged resources are not prepared.")
datas = [(str(staging / "resource"), "resource"),
         (str(staging / "tiktoken_cache"), "tiktoken_cache"),
         (str(project_root / "CHANGELOG.md"), "."),
         (str(project_root / "LICENSE"), ".")]
for name in ("android_build_runner.py", "rpatool_core.py"):
    datas.append((str(project_root / "module" / "Tool" / name), "module/Tool"))

# Agent tools and provider SDKs are imported with importlib at runtime.
hiddenimports = ["update_integrity", "update_path_policy", "unrpa"]
for package in ("api", "base", "module", "utils"):
    for source in (project_root / package).rglob("*.py"):
        if "__pycache__" not in source.parts:
            parts = list(source.relative_to(project_root).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            hiddenimports.append(".".join(parts))

binaries = []
for package in ("opencc", "tiktoken", "pygtrans", "translators", "json_repair"):
    pkg_data, pkg_binaries, pkg_imports = collect_all(package)
    datas += pkg_data
    binaries += pkg_binaries
    hiddenimports += pkg_imports
for package in ("openai", "anthropic", "google.genai", "google.auth",
                "httpx", "tiktoken_ext", "uvicorn", "websockets"):
    hiddenimports += collect_submodules(package)
    datas += collect_data_files(package)
for distribution in ("google-genai", "openai", "anthropic", "tiktoken", "uvicorn"):
    datas += copy_metadata(distribution)

a = Analysis(
    [str(project_root / "desktop" / "sidecar" / "main.py")],
    pathex=[str(project_root)],
    binaries=binaries, datas=datas, hiddenimports=sorted(set(hiddenimports)),
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "qfluentwidgets",
              "frontend", "widget", "tkinter", "IPython", "notebook",
              "pytest", "torch", "tensorflow", "transformers", "spacy",
              "scipy", "matplotlib", "sklearn", "pyarrow", "tables"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="RenpyBoxBackend",
    console=True, upx=False, icon=str(staging / "resource" / "icon.ico"),
)
collect = COLLECT(exe, a.binaries, a.datas, name="backend", upx=False)
