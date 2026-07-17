from base.VersionManager import VersionManager


def test_parse_version_accepts_app_and_release_formats() -> None:
    assert VersionManager.parse_version("v0.60") == (0, 60, 0, 0)
    assert VersionManager.parse_version("RenpyBox_v0.60") == (0, 60, 0, 0)
    assert VersionManager.parse_version("v0.5.13") == (0, 5, 13, 0)
