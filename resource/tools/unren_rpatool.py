#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import os
import sys


def _detect_archive_extensions(renpy_loader):
    archive_extensions = []

    # Prefer loader helper if present (some versions expose get_supported_extensions()).
    try:
        get_exts = getattr(renpy_loader, "get_supported_extensions", None)
        if callable(get_exts):
            for ext in get_exts() or []:
                if ext not in archive_extensions:
                    archive_extensions.append(ext)
            if archive_extensions:
                return archive_extensions
    except Exception:
        pass

    # Newer Ren'Py uses ArchiveHandlers object with .exts dict (not iterable).
    try:
        archive_handlers = getattr(renpy_loader, "archive_handlers", None)
        if archive_handlers is not None:
            exts = getattr(archive_handlers, "exts", None)
            if isinstance(exts, dict):
                for ext in exts.keys():
                    if ext not in archive_extensions:
                        archive_extensions.append(ext)
                if archive_extensions:
                    return archive_extensions

            # Older versions may still allow iteration of handlers.
            try:
                for handler in archive_handlers:
                    for ext in handler.get_supported_extensions():
                        if ext not in archive_extensions:
                            archive_extensions.append(ext)
            except TypeError:
                pass
    except Exception:
        pass

    # Fallback to .rpa if detection fails.
    return archive_extensions or [".rpa"]


class RenPyArchive:
    file = None
    handle = None

    files = {}
    indexes = {}

    def __init__(self, file, index, renpy_config, renpy_loader):
        self._renpy_config = renpy_config
        self._renpy_loader = renpy_loader
        self.load(file, index)

    def convert_filename(self, filename):
        (drive, filename) = os.path.splitdrive(os.path.normpath(filename).replace(os.sep, "/"))
        return filename

    def list(self):
        return list(self.indexes)

    def read(self, filename):
        filename = self.convert_filename(filename)
        if filename != "." and isinstance(self.indexes[filename], list):
            if hasattr(self._renpy_loader, "load_from_archive"):
                subfile = self._renpy_loader.load_from_archive(filename)
            else:
                subfile = self._renpy_loader.load_core(filename)
            return subfile.read()
        return None

    def load(self, filename, index):
        self.file = filename
        self.files = {}
        self.indexes = {}
        self.handle = open(self.file, "rb")

        base, ext = filename.rsplit(".", 1)
        # Newer Ren'Py versions require arc_files to be populated before index_archives.
        # Build a minimal arc_files list for this archive to avoid global scans.
        try:
            if hasattr(self._renpy_loader, "arc_files") and hasattr(self._renpy_loader, "index_archives"):
                archive_path = os.path.realpath(self.file)
                arc_ext = "." + ext
                self._renpy_loader.arc_files = [(base, arc_ext, archive_path)]
                if hasattr(self._renpy_loader, "archives"):
                    try:
                        self._renpy_loader.archives.clear()
                    except Exception:
                        self._renpy_loader.archives = []
                self._renpy_loader.index_archives()
                if getattr(self._renpy_loader, "archives", None):
                    items = self._renpy_loader.archives[0][1].items()
                else:
                    raise Exception("index_archives returned empty")
            else:
                raise Exception("no arc_files/index_archives")
        except Exception:
            # Fallback to legacy flow using searchpath + archives.
            self._renpy_config.archives.append(base)
            self._renpy_config.searchpath = [os.path.dirname(os.path.realpath(self.file))]
            self._renpy_config.basedir = os.path.dirname(self._renpy_config.searchpath[0])

            self._renpy_loader.index_archives()
            items = self._renpy_loader.archives[index][1].items()

        for file, index in items:
            self.indexes[file] = index


def main(argv):
    parser = argparse.ArgumentParser(
        description="UnRen-style Ren'Py archive extractor (runs with game's python).",
        add_help=True,
    )
    parser.add_argument(
        "-r",
        action="store_true",
        dest="remove",
        help="Delete archives after unpacking.",
    )
    parser.add_argument(
        "--script-only",
        action="store_true",
        dest="script_only",
        help="Only extract .rpy/.rpyc files.",
    )
    parser.add_argument(
        "dir",
        type=str,
        help="The Ren'Py game directory to operate on (usually ./game/).",
    )
    args = parser.parse_args(argv)

    directory = os.path.abspath(args.dir)
    if not os.path.isdir(directory):
        print("Error: directory does not exist: {0}".format(directory))
        return 1

    os.chdir(directory)
    sys.path.insert(0, os.path.abspath(os.path.join(directory, os.pardir)))

    # Ensure the game's Ren'Py package wins over any shadowing modules.
    for key in list(sys.modules):
        if key == "renpy" or key.startswith("renpy."):
            del sys.modules[key]

    try:
        # Some Ren'Py versions reference renpy.error during renpy.config import.
        import renpy.error  # noqa: F401
        import renpy.object  # noqa: F401
        import renpy.config as renpy_config
        import renpy.loader as renpy_loader
    except Exception as exc:
        print("Error: failed to import renpy modules: {0}".format(exc))
        return 1

    try:
        if hasattr(renpy_config, "archives"):
            renpy_config.archives = []
    except Exception:
        pass

    archive_extensions = _detect_archive_extensions(renpy_loader)

    archives = []
    for file in os.listdir(directory):
        if not os.path.isfile(os.path.join(directory, file)):
            continue
        try:
            base, ext = file.rsplit(".", 1)
            if "." + ext in archive_extensions:
                archives.append(file)
        except Exception:
            pass

    if not archives:
        print("  There are no archives in the game folder.")
        return 0

    output = "."
    for arch in archives:
        print('  Unpacking "{0}" archive.'.format(arch))
        archive = RenPyArchive(arch, archives.index(arch), renpy_config, renpy_loader)
        files = archive.list()

        if not os.path.exists(output):
            os.makedirs(output)

        for filename in files:
            if args.script_only and not (filename.endswith(".rpy") or filename.endswith(".rpyc")):
                continue

            outfile = filename
            contents = archive.read(filename)
            if contents is None:
                continue

            out_path = os.path.join(output, outfile)
            out_dir = os.path.dirname(out_path)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir)

            with open(out_path, "wb") as fp:
                fp.write(contents)

    print("  All archives unpacked.")

    if args.remove:
        for arch in archives:
            try:
                os.remove(os.path.join(directory, arch))
                print("  Archive {0} has been deleted.".format(arch))
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


