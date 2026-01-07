#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import os
import sys


def _detect_archive_extensions(renpy_loader):
    archive_extensions = []
    if hasattr(renpy_loader, "archive_handlers"):
        for handler in renpy_loader.archive_handlers:
            for ext in handler.get_supported_extensions():
                if ext not in archive_extensions:
                    archive_extensions.append(ext)
    else:
        archive_extensions.append(".rpa")
    return archive_extensions


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
    sys.path.append(os.path.abspath(os.path.join(directory, os.pardir)))

    try:
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

