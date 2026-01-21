from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys


def _add_rapt_to_path(sdk_root: str) -> None:
    buildlib = os.path.join(sdk_root, "rapt", "buildlib")
    if buildlib not in sys.path:
        sys.path.insert(0, buildlib)


def _add_sdk_to_path(sdk_root: str) -> None:
    renpy_dir = os.path.join(sdk_root, "renpy")
    renpy_dir_norm = os.path.normcase(os.path.abspath(renpy_dir))
    sys.path[:] = [
        p
        for p in sys.path
        if not p or os.path.normcase(os.path.abspath(p)) != renpy_dir_norm
    ]
    if sdk_root not in sys.path:
        sys.path.insert(0, sdk_root)


def _make_interface(default_input: str | None = None, auto_yes: bool = True):
    import rapt.interface as interface

    class NonInteractiveInterface(interface.Interface):
        def __init__(self, default_input: str | None, auto_yes: bool):
            super().__init__()
            self._default_input = default_input
            self._auto_yes = auto_yes

        def input(self, prompt, empty=None):  # noqa: A002 - keep API parity
            if self._default_input:
                self.write(prompt)
                return self._default_input
            if empty is not None:
                self.write(prompt)
                return empty
            self.write(prompt)
            return ""

        def yesno(self, prompt):
            self.write(prompt)
            return self._auto_yes

        def yesno_choice(self, prompt, default=None):
            self.write(prompt)
            if default is not None:
                return default
            return self._auto_yes

        def terms(self, url, prompt):
            self.write(prompt)
            return self._auto_yes

        def open_directory(self, directory, prompt):
            self.write(prompt)
            return None

    return NonInteractiveInterface(default_input, auto_yes)


def _setup_rapt(sdk_root: str) -> None:
    _add_sdk_to_path(sdk_root)
    _add_rapt_to_path(sdk_root)
    import rapt.plat as plat

    plat.renpy = True
    plat.translate = lambda s: s


def _escape_properties_value(value: str) -> str:
    return value.encode("unicode_escape").decode("ascii")


def _rewrite_property(path: str, key: str, value: str) -> None:
    try:
        with open(path, "rb") as reader:
            raw_lines = reader.read().splitlines()
    except FileNotFoundError:
        raw_lines = []

    lines = []
    replaced = False
    for raw_line in raw_lines:
        line = raw_line.decode("latin-1")
        if line.strip().startswith(f"{key}="):
            lines.append(f"{key}={value}")
            replaced = True
        else:
            lines.append(line)

    if not replaced:
        lines.append(f"{key}={value}")

    with open(path, "wb") as writer:
        writer.write(("\n".join(lines) + "\n").encode("latin-1"))


def _patch_key_store_properties() -> None:
    import rapt.keys as keys
    import rapt.properties as properties

    original_update = keys.update_project_keys

    def update_project_keys(base: str) -> None:
        original_update(base)
        default_path = os.path.abspath(keys.default_keystore_path(base)).replace("\\", "/")
        bundle_path = os.path.abspath(keys.bundle_keystore_path(base)).replace("\\", "/")
        _rewrite_property(
            properties.local_properties,
            "key.store",
            _escape_properties_value(default_path),
        )
        _rewrite_property(
            properties.bundle_properties,
            "key.store",
            _escape_properties_value(bundle_path),
        )

    keys.update_project_keys = update_project_keys


def _patch_long_path_zip() -> None:
    if os.name != "nt":
        return
    import rapt.install_sdk as install_sdk
    import zipfile

    def _to_long_path(path: str) -> str:
        if path.startswith("\\\\?\\"):
            return path
        if path.startswith("\\\\"):
            return "\\\\?\\UNC\\" + path[2:]
        return "\\\\?\\" + os.path.normpath(path)

    def _maybe_long_path(path: str) -> str:
        abs_path = os.path.abspath(path)
        if len(abs_path) >= 240:
            return _to_long_path(abs_path)
        return abs_path

    def _extract_member(self, member, targetpath, pwd):
        if not isinstance(member, zipfile.ZipInfo):
            member = self.getinfo(member)

        arcname = member.filename.replace("/", os.path.sep)

        if os.path.altsep:
            arcname = arcname.replace(os.path.altsep, os.path.sep)

        arcname = os.path.splitdrive(arcname)[1]
        invalid_path_parts = ("", os.path.curdir, os.path.pardir)
        arcname = os.path.sep.join(
            x for x in arcname.split(os.path.sep) if x not in invalid_path_parts
        )

        targetpath = os.path.normpath(os.path.join(targetpath, arcname))
        targetpath_fs = _maybe_long_path(targetpath)

        upperdirs = os.path.dirname(targetpath_fs)
        if upperdirs and not os.path.exists(upperdirs):
            os.makedirs(upperdirs)

        if member.filename[-1] == "/":
            if not os.path.isdir(targetpath_fs):
                os.mkdir(targetpath_fs)
            return targetpath

        attr = member.external_attr >> 16

        if stat.S_ISLNK(attr):
            with self.open(member, pwd=pwd) as source:
                linkto = source.read()
            os.symlink(linkto, targetpath_fs)
        else:
            with self.open(member, pwd=pwd) as source, open(targetpath_fs, "wb") as target:
                shutil.copyfileobj(source, target)
            if attr:
                os.chmod(targetpath_fs, attr)

        return targetpath

    install_sdk._FixedZipFile._extract_member = _extract_member


def _has_heap_setting(value: str) -> bool:
    return "-xmx" in value.lower()


def _ensure_gradle_heap(sdk_root: str, iface) -> None:
    heap_args = os.environ.get("RENPY_GRADLE_JVMARGS", "-Xmx4g -Xms512m")
    os.environ["ORG_GRADLE_PROJECT_org.gradle.jvmargs"] = heap_args
    if not _has_heap_setting(os.environ.get("GRADLE_OPTS", "")):
        os.environ["GRADLE_OPTS"] = heap_args

    for rel_path in ("rapt\\prototype\\gradle.properties", "rapt\\project\\gradle.properties"):
        prop_path = os.path.join(sdk_root, rel_path)
        _rewrite_property(prop_path, "org.gradle.jvmargs", heap_args)

    try:
        iface.write(f"已设置 Gradle JVM 内存: {heap_args}")
    except Exception:
        pass


def install_sdk(args: argparse.Namespace) -> int:
    _setup_rapt(args.sdk)
    _patch_long_path_zip()
    import rapt.install_sdk as install_sdk

    iface = _make_interface(default_input=args.dname, auto_yes=args.auto_yes)
    install_sdk.install_sdk(iface)
    return 0


def generate_keys(args: argparse.Namespace) -> int:
    _setup_rapt(args.sdk)
    import rapt.keys as keys

    iface = _make_interface(default_input=args.dname, auto_yes=args.auto_yes)
    keys.generate_keys(iface, args.project)
    return 0


def build_android(args: argparse.Namespace) -> int:
    _setup_rapt(args.sdk)
    _patch_key_store_properties()
    import rapt.build as build

    iface = _make_interface()
    _ensure_gradle_heap(args.sdk, iface)
    build.build(
        iface,
        args.dist,
        args.project,
        install=args.install,
        launch=args.launch,
    )
    return 0


def distclean(args: argparse.Namespace) -> int:
    _setup_rapt(args.sdk)
    import rapt.build as build

    iface = _make_interface()
    build.distclean(iface)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ren'Py Android build helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install_sdk", help="Install Android SDK")
    install.add_argument("--sdk", required=True)
    install.add_argument("--auto-yes", action="store_true", default=True)
    install.add_argument("--dname", default=None)

    keys = subparsers.add_parser("generate_keys", help="Generate keystore files")
    keys.add_argument("--sdk", required=True)
    keys.add_argument("--project", required=True)
    keys.add_argument("--auto-yes", action="store_true", default=True)
    keys.add_argument("--dname", default=None)

    build = subparsers.add_parser("build", help="Build Android package")
    build.add_argument("--sdk", required=True)
    build.add_argument("--project", required=True)
    build.add_argument("--dist", required=True)
    build.add_argument("--install", action="store_true", default=False)
    build.add_argument("--launch", action="store_true", default=False)

    clean = subparsers.add_parser("distclean", help="Clean Android build artifacts")
    clean.add_argument("--sdk", required=True)

    args = parser.parse_args()

    if args.command == "install_sdk":
        return install_sdk(args)
    if args.command == "generate_keys":
        return generate_keys(args)
    if args.command == "build":
        return build_android(args)
    if args.command == "distclean":
        return distclean(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
