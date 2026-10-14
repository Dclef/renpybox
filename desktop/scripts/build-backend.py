"""Build the API runtime from tracked assets without embedding local credentials."""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "desktop" / "runtime"
STAGING = RUNTIME / "staging"
MANIFEST = RUNTIME / "backend" / "build-manifest.json"
REQUIRED = ("PyInstaller", "fastapi", "uvicorn", "opencc", "translators",
            "pygtrans", "openpyxl", "yaml", "lxml", "bs4", "tiktoken",
            "regex", "json_repair", "rich", "httpx", "openai", "anthropic",
            "google.genai", "unrpa", "pandas", "websockets", "truststore")
PRIVATE_NAMES = {"config.json", "secrets.json", "credentials.json", "build_sanitized_config.json"}


def tracked_resources() -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z", "--", "resource"],
                            cwd=ROOT, capture_output=True, check=True)
    paths = []
    for item in result.stdout.decode("utf-8").split("\0"):
        if not item:
            continue
        relative = Path(item)
        if relative.name.casefold() in PRIVATE_NAMES or relative.name.startswith(".env"):
            continue
        if "__pycache__" in relative.parts or relative.suffix == ".pyc":
            continue
        source = ROOT / relative
        if not source.is_file() or source.is_symlink():
            raise RuntimeError(f"Tracked build resource is missing or symlinked: {relative}")
        paths.append(relative)
    if Path("resource/icon.ico") not in paths:
        raise RuntimeError("The original tracked resource/icon.ico is required.")
    return sorted(paths)


def fingerprint(resources: list[Path]) -> str:
    sources = set(resources)
    for directory in ("api", "base", "module", "utils", "desktop/sidecar"):
        for source in (ROOT / directory).rglob("*"):
            if source.is_file() and source.suffix in {".py", ".spec", ".txt", ".mjs"} and "__pycache__" not in source.parts:
                sources.add(source.relative_to(ROOT))
    for name in ("update_integrity.py", "update_path_policy.py", "CHANGELOG.md", "LICENSE",
                 "desktop/scripts/build-backend.py", "desktop/scripts/requirements-backend.txt"):
        sources.add(Path(name))
    digest = hashlib.sha256()
    digest.update(sys.version.encode())
    for distribution in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata.get("Name", "")):
        digest.update(f"{distribution.metadata.get('Name')}=={distribution.version}\n".encode())
    for source in sorted(sources):
        digest.update(source.as_posix().encode())
        digest.update((ROOT / source).read_bytes())
    return digest.hexdigest()


def main() -> None:
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise RuntimeError("Use 64-bit Python on Windows to build this backend.")
    missing = []
    for module in REQUIRED:
        try:
            found = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            found = False
        if not found:
            missing.append(module)
    if missing:
        raise RuntimeError("Missing build dependencies: " + ", ".join(missing) +
                           ". Run python -m pip install -r desktop/scripts/requirements-backend.txt")
    resources = tracked_resources()
    signature = fingerprint(resources)
    executable = RUNTIME / "backend" / "RenpyBoxBackend.exe"
    if "--force" not in sys.argv and MANIFEST.is_file() and executable.is_file():
        if json.loads(MANIFEST.read_text(encoding="utf-8")).get("fingerprint") == signature:
            print("[backend] Inputs unchanged; reusing verified frozen runtime.", flush=True)
            return
    # Only the private staging directory is replaced; existing installer artifacts
    # and the last successful backend remain available while this build runs.
    if STAGING.exists():
        if STAGING.resolve().parent != RUNTIME.resolve():
            raise RuntimeError("Invalid build staging directory")
        shutil.rmtree(STAGING)
    STAGING.mkdir(parents=True)
    for relative in resources:
        target = STAGING / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    # Bundle the exact token dictionaries used by CacheItem for offline startup.
    os.environ["TIKTOKEN_CACHE_DIR"] = str(STAGING / "tiktoken_cache")
    os.environ.setdefault("translators_default_region", "CN")
    import tiktoken
    for encoding in ("o200k_base", "cl100k_base"):
        tiktoken.get_encoding(encoding)
    print(f"[backend] Freezing API runtime and {len(resources)} tracked resources.", flush=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm",
                    "--distpath", str(RUNTIME), "--workpath", str(RUNTIME / "pyinstaller"),
                    str(ROOT / "desktop" / "sidecar" / "sidecar.spec")], cwd=ROOT, check=True)
    if not executable.is_file():
        raise RuntimeError("PyInstaller did not produce RenpyBoxBackend.exe")
    # A fresh directory and explicit appRoot keep packaging checks away from the
    # developer's configuration and Windows credentials.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="renpybox-backend-check-") as temporary:
        env = {**os.environ, "RENPYBOX_APP_ROOT": temporary, "PYTHONPATH": ""}
        env.pop("RENPYBOX_RESOURCE_ROOT", None)
        env.pop("TIKTOKEN_CACHE_DIR", None)
        subprocess.run([str(executable), "--self-test"], cwd=temporary, env=env, check=True, timeout=90)
    MANIFEST.write_text(json.dumps({"fingerprint": signature, "python": sys.version.split()[0],
                                    "resource_count": len(resources)}, indent=2) + "\n", encoding="utf-8")
    print("[backend] Frozen runtime passed its isolated self-test.", flush=True)


if __name__ == "__main__":
    main()
