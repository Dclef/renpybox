from module.Config import Config


def test_manual_ui_scale_factors_never_reduce_device_pixel_ratio() -> None:
    assert tuple(Config.UI_SCALE_FACTORS) == ("125%", "150%", "175%", "200%")
    assert all(float(value) >= 1 for value in Config.UI_SCALE_FACTORS.values())


def test_removed_scale_factor_is_reset_to_auto() -> None:
    for legacy in ("50%", "75%", "unexpected"):
        assert Config.migrate_dict({"scale_factor": legacy})["scale_factor"] == ""


def test_supported_scale_factor_is_preserved() -> None:
    assert Config.migrate_dict({"scale_factor": "150%"})["scale_factor"] == "150%"
    assert Config.migrate_dict({"scale_factor": ""})["scale_factor"] == ""
