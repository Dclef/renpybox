"""
Package initializer for the `base` module.

This file makes `oldcatporject.base` a proper package so runtime
imports like `from base.LogManager import LogManager` work correctly
and PyInstaller can include the package when building the executable.

The file is intentionally minimal.
"""

__all__ = []
