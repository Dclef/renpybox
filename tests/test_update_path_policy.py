import stat
import zipfile

import pytest

from update_path_policy import validate_relative_path, validate_zip_members


@pytest.mark.parametrize(
    "path",
    [
        "../victim.txt",
        "..\\victim.txt",
        "C:/victim.txt",
        "/victim.txt",
        "folder/../victim.txt",
        "CON.txt",
        "folder:stream.txt",
        "trailing.",
    ],
)
def test_validate_relative_path_rejects_windows_escape_forms(path: str) -> None:
    with pytest.raises(RuntimeError):
        validate_relative_path(path)


def test_validate_zip_members_rejects_case_and_parent_collisions() -> None:
    with pytest.raises(RuntimeError, match="Ambiguous"):
        validate_zip_members(
            [zipfile.ZipInfo("Folder/file.txt"), zipfile.ZipInfo("folder/FILE.TXT")],
            label="test ZIP",
        )

    with pytest.raises(RuntimeError, match="parent"):
        validate_zip_members(
            [zipfile.ZipInfo("folder"), zipfile.ZipInfo("folder/file.txt")],
            label="test ZIP",
        )


def test_validate_zip_members_rejects_symlink_member() -> None:
    member = zipfile.ZipInfo("link.txt")
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16

    with pytest.raises(RuntimeError, match="member type"):
        validate_zip_members([member], label="test ZIP")


def test_validate_zip_members_allows_nested_regular_files() -> None:
    members = validate_zip_members(
        [zipfile.ZipInfo("nested/file.txt")],
        label="test ZIP",
    )
    assert members == {"nested/file.txt"}
