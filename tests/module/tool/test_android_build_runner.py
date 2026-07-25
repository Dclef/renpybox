from module.Tool.android_build_runner import _ensure_backup_resource


def test_ensure_backup_resource_restores_missing_project_file(tmp_path) -> None:
    source = tmp_path / "rapt" / "prototype" / "app" / "src" / "main" / "res" / "xml" / "backup.xml"
    target = tmp_path / "rapt" / "project" / "app" / "src" / "main" / "res" / "xml" / "backup.xml"
    source.parent.mkdir(parents=True)
    target.parent.parent.parent.parent.parent.mkdir(parents=True)
    source.write_text("<full-backup-content />", encoding="utf-8")

    _ensure_backup_resource(str(tmp_path))

    assert target.read_text(encoding="utf-8") == "<full-backup-content />"
