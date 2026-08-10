# RenpyBox 内置修改器：只使用 Ren'Py 原生样式和操作。

default persistent._rb_sm_dialogue_enabled = True
default persistent._rb_sm_dialogue_size = 37
default persistent._rb_sm_dialogue_width = 1616
default persistent._rb_sm_dialogue_xoffset = 0
default persistent._rb_sm_dialogue_yoffset = 0
default persistent._rb_sm_dialogue_color = "#FFFFFF"
default persistent._rb_sm_dialogue_outline = 3
default persistent._rb_sm_name_size = 42
default persistent._rb_sm_name_xoffset = 0
default persistent._rb_sm_name_yoffset = 0
default persistent._rb_sm_window_alpha = 1.0

default persistent._rb_sm_choice_enabled = True
default persistent._rb_sm_choice_size = 30
default persistent._rb_sm_choice_width = 1100
default persistent._rb_sm_choice_xoffset = 0
default persistent._rb_sm_choice_yoffset = 0
default persistent._rb_sm_choice_color = "#FFFFFF"
default persistent._rb_sm_choice_align = "center"
default persistent._rb_sm_choice_background = True

default persistent._rb_sm_quick_menu_enabled = False
default persistent._rb_sm_quick_return = True
default persistent._rb_sm_quick_history = True
default persistent._rb_sm_quick_hide = True
default persistent._rb_sm_quick_skip = True
default persistent._rb_sm_quick_auto = False
default persistent._rb_sm_quick_save = True
default persistent._rb_sm_quick_load = True
default persistent._rb_sm_quick_quicksave = True
default persistent._rb_sm_quick_quickload = True
default persistent._rb_sm_quick_preferences = True

init -1100 python:
    # 画廊 Hook 用这个标记判断是否可以显示第三个入口。
    _rb_simple_modifier_available = True

    _rb_sm_original_styles = {}
    _rb_sm_quick_menu_last_enabled = False

init -1000 python:
    def _rb_sm_get(name, fallback):
        try:
            return getattr(persistent, name)
        except Exception:
            return fallback

    def _rb_sm_has_gallery_panel():
        return bool(globals().get("_rb_gallery_installed", False))

    def _rb_sm_is_main_menu():
        return bool(globals().get("main_menu", False))

    def _rb_sm_capture_styles():
        if _rb_sm_original_styles:
            return

        style_fields = {
            "say_dialogue": ("size", "xsize", "color", "outlines"),
            "say_label": ("size", "xoffset", "yoffset"),
            "say_window": ("xoffset", "yoffset", "background"),
            "choice_button_text": ("size", "color", "xalign"),
            "choice_button": ("xsize", "xoffset", "yoffset", "background"),
        }
        for style_name, fields in style_fields.items():
            try:
                style_object = getattr(style, style_name)
            except Exception:
                continue
            for field_name in fields:
                try:
                    _rb_sm_original_styles[(style_name, field_name)] = getattr(
                        style_object, field_name
                    )
                except Exception:
                    pass

    def _rb_sm_set_style(style_name, field_name, value):
        try:
            setattr(getattr(style, style_name), field_name, value)
        except Exception:
            pass

    def _rb_sm_window_background(alpha):
        original = _rb_sm_original_styles.get(("say_window", "background"))
        if alpha >= 0.999:
            return original
        try:
            return Transform(original, alpha=alpha)
        except Exception:
            return original

    def _rb_sm_restore(prefix):
        for style_key, value in _rb_sm_original_styles.items():
            style_name, field_name = style_key
            if style_name.startswith(prefix):
                _rb_sm_set_style(style_name, field_name, value)

    def _rb_sm_apply_styles():
        _rb_sm_capture_styles()

        if _rb_sm_get("_rb_sm_dialogue_enabled", True):
            _rb_sm_set_style(
                "say_dialogue", "size", _rb_sm_get("_rb_sm_dialogue_size", 37)
            )
            _rb_sm_set_style(
                "say_dialogue", "xsize", _rb_sm_get("_rb_sm_dialogue_width", 1616)
            )
            _rb_sm_set_style(
                "say_dialogue", "color", _rb_sm_get("_rb_sm_dialogue_color", "#FFFFFF")
            )
            _rb_sm_set_style(
                "say_dialogue",
                "outlines",
                [
                    (
                        _rb_sm_get("_rb_sm_dialogue_outline", 3),
                        "#000000",
                        0,
                        0,
                    )
                ],
            )
            _rb_sm_set_style(
                "say_label", "size", _rb_sm_get("_rb_sm_name_size", 42)
            )
            _rb_sm_set_style(
                "say_label", "xoffset", _rb_sm_get("_rb_sm_name_xoffset", 0)
            )
            _rb_sm_set_style(
                "say_label", "yoffset", _rb_sm_get("_rb_sm_name_yoffset", 0)
            )
            _rb_sm_set_style(
                "say_window", "xoffset", _rb_sm_get("_rb_sm_dialogue_xoffset", 0)
            )
            _rb_sm_set_style(
                "say_window", "yoffset", _rb_sm_get("_rb_sm_dialogue_yoffset", 0)
            )
            _rb_sm_set_style(
                "say_window",
                "background",
                _rb_sm_window_background(_rb_sm_get("_rb_sm_window_alpha", 1.0)),
            )
        else:
            _rb_sm_restore("say_")

        if _rb_sm_get("_rb_sm_choice_enabled", True):
            _rb_sm_set_style(
                "choice_button_text", "size", _rb_sm_get("_rb_sm_choice_size", 30)
            )
            _rb_sm_set_style(
                "choice_button_text",
                "color",
                _rb_sm_get("_rb_sm_choice_color", "#FFFFFF"),
            )
            _rb_sm_set_style(
                "choice_button_text",
                "xalign",
                {"left": 0.0, "center": 0.5, "right": 1.0}.get(
                    _rb_sm_get("_rb_sm_choice_align", "center"), 0.5
                ),
            )
            _rb_sm_set_style(
                "choice_button", "xsize", _rb_sm_get("_rb_sm_choice_width", 1100)
            )
            _rb_sm_set_style(
                "choice_button", "xoffset", _rb_sm_get("_rb_sm_choice_xoffset", 0)
            )
            _rb_sm_set_style(
                "choice_button", "yoffset", _rb_sm_get("_rb_sm_choice_yoffset", 0)
            )
            if _rb_sm_get("_rb_sm_choice_background", True):
                _rb_sm_restore("choice_button")
                _rb_sm_set_style(
                    "choice_button", "xsize", _rb_sm_get("_rb_sm_choice_width", 1100)
                )
                _rb_sm_set_style(
                    "choice_button", "xoffset", _rb_sm_get("_rb_sm_choice_xoffset", 0)
                )
                _rb_sm_set_style(
                    "choice_button", "yoffset", _rb_sm_get("_rb_sm_choice_yoffset", 0)
                )
            else:
                _rb_sm_set_style("choice_button", "background", None)
        else:
            _rb_sm_restore("choice_")

        try:
            renpy.style.rebuild()
        except Exception:
            pass

    def _rb_sm_set(name, value):
        setattr(persistent, name, value)
        _rb_sm_apply_styles()
        try:
            renpy.restart_interaction()
        except Exception:
            pass

    def _rb_sm_step(name, amount, minimum, maximum):
        current = _rb_sm_get(name, minimum)
        try:
            value = current + amount
        except Exception:
            value = minimum
        _rb_sm_set(name, max(minimum, min(maximum, value)))

    def _rb_sm_toggle(name):
        _rb_sm_set(name, not bool(_rb_sm_get(name, False)))

    def _rb_sm_reset():
        defaults = {
            "_rb_sm_dialogue_enabled": True,
            "_rb_sm_dialogue_size": 37,
            "_rb_sm_dialogue_width": 1616,
            "_rb_sm_dialogue_xoffset": 0,
            "_rb_sm_dialogue_yoffset": 0,
            "_rb_sm_dialogue_color": "#FFFFFF",
            "_rb_sm_dialogue_outline": 3,
            "_rb_sm_name_size": 42,
            "_rb_sm_name_xoffset": 0,
            "_rb_sm_name_yoffset": 0,
            "_rb_sm_window_alpha": 1.0,
            "_rb_sm_choice_enabled": True,
            "_rb_sm_choice_size": 30,
            "_rb_sm_choice_width": 1100,
            "_rb_sm_choice_xoffset": 0,
            "_rb_sm_choice_yoffset": 0,
            "_rb_sm_choice_color": "#FFFFFF",
            "_rb_sm_choice_align": "center",
            "_rb_sm_choice_background": True,
            "_rb_sm_quick_menu_enabled": False,
            "_rb_sm_quick_return": True,
            "_rb_sm_quick_history": True,
            "_rb_sm_quick_hide": True,
            "_rb_sm_quick_skip": True,
            "_rb_sm_quick_auto": False,
            "_rb_sm_quick_save": True,
            "_rb_sm_quick_load": True,
            "_rb_sm_quick_quicksave": True,
            "_rb_sm_quick_quickload": True,
            "_rb_sm_quick_preferences": True,
        }
        for name, value in defaults.items():
            setattr(persistent, name, value)
        _rb_sm_apply_styles()
        try:
            renpy.restart_interaction()
        except Exception:
            pass

    def _rb_sm_control_quick_menu():
        global _rb_sm_quick_menu_last_enabled
        try:
            if _rb_sm_is_main_menu():
                renpy.hide_screen("_rb_simple_quick_menu")
                return
            enabled = bool(_rb_sm_get("_rb_sm_quick_menu_enabled", False))
            if enabled:
                renpy.hide_screen("quick_menu")
                renpy.show_screen("_rb_simple_quick_menu")
            elif _rb_sm_quick_menu_last_enabled:
                renpy.hide_screen("_rb_simple_quick_menu")
                renpy.show_screen("quick_menu")
            else:
                renpy.hide_screen("_rb_simple_quick_menu")
            _rb_sm_quick_menu_last_enabled = enabled
        except Exception:
            pass

init 1000 python:
    _rb_sm_apply_styles()
    if _rb_sm_control_quick_menu not in config.interact_callbacks:
        config.interact_callbacks.append(_rb_sm_control_quick_menu)
    if "_rb_simple_modifier_toggle" not in config.overlay_screens:
        config.overlay_screens.append("_rb_simple_modifier_toggle")

screen _rb_simple_modifier_toggle():
    zorder 100

    if not _rb_sm_has_gallery_panel():
        key "K_F9" action ToggleScreen("_rb_simple_modifier")

        frame:
            xalign 0.98
            yalign 0.02
            xpadding 10
            ypadding 6

            textbutton "内置修改器":
                action Show("_rb_simple_modifier")

screen _rb_simple_modifier():
    zorder 102
    modal True

    if _rb_sm_has_gallery_panel():
        key "K_F9" action [Hide("_rb_simple_modifier"), Show("_rb_game_tools")]
    else:
        key "K_F9" action Hide("_rb_simple_modifier")

    frame:
        xalign 0.5
        yalign 0.5
        xsize 900
        ysize 820
        xpadding 18
        ypadding 16

        vbox:
            spacing 8

            hbox:
                xfill True
                text "内置修改器（RenpyBox）" size 24
                null width 20
                if _rb_sm_has_gallery_panel():
                    textbutton "返回":
                        action [Hide("_rb_simple_modifier"), Show("_rb_game_tools")]
                else:
                    textbutton "关闭":
                        action Hide("_rb_simple_modifier")

            text "提供对话框、选项框和快捷菜单调整；仅对使用 Ren'Py 默认界面的游戏生效。" size 14

            viewport:
                ysize 735
                mousewheel True
                scrollbars "vertical"

                vbox:
                    spacing 10

                    text "对话框设置" size 20
                    hbox:
                        spacing 8
                        text "对话框模组" xsize 220
                        textbutton ("启用" if persistent._rb_sm_dialogue_enabled else "禁用"):
                            action Function(_rb_sm_toggle, "_rb_sm_dialogue_enabled")
                        text "关闭后恢复游戏原本的对话框样式" size 13

                    hbox:
                        spacing 8
                        text "对话文字大小：%s" % persistent._rb_sm_dialogue_size xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_dialogue_size", -1, 12, 75)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_dialogue_size", 1, 12, 75)

                    hbox:
                        spacing 8
                        text "对话文字宽度：%s" % persistent._rb_sm_dialogue_width xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_dialogue_width", -40, 400, 1920)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_dialogue_width", 40, 400, 1920)

                    hbox:
                        spacing 8
                        text "对话框横向位置：%s" % persistent._rb_sm_dialogue_xoffset xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_dialogue_xoffset", -10, -960, 960)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_dialogue_xoffset", 10, -960, 960)

                    hbox:
                        spacing 8
                        text "对话框纵向位置：%s" % persistent._rb_sm_dialogue_yoffset xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_dialogue_yoffset", -10, -960, 960)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_dialogue_yoffset", 10, -960, 960)

                    hbox:
                        spacing 8
                        text "名字文字大小：%s" % persistent._rb_sm_name_size xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_name_size", -1, 12, 75)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_name_size", 1, 12, 75)

                    hbox:
                        spacing 8
                        text "名字横向位置：%s" % persistent._rb_sm_name_xoffset xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_name_xoffset", -10, -960, 960)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_name_xoffset", 10, -960, 960)

                    hbox:
                        spacing 8
                        text "名字纵向位置：%s" % persistent._rb_sm_name_yoffset xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_name_yoffset", -10, -960, 960)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_name_yoffset", 10, -960, 960)

                    hbox:
                        spacing 8
                        text "背景透明度" xsize 220
                        textbutton "0%":
                            action Function(_rb_sm_set, "_rb_sm_window_alpha", 0.0)
                        textbutton "25%":
                            action Function(_rb_sm_set, "_rb_sm_window_alpha", 0.25)
                        textbutton "50%":
                            action Function(_rb_sm_set, "_rb_sm_window_alpha", 0.5)
                        textbutton "75%":
                            action Function(_rb_sm_set, "_rb_sm_window_alpha", 0.75)
                        textbutton "100%":
                            action Function(_rb_sm_set, "_rb_sm_window_alpha", 1.0)

                    hbox:
                        spacing 8
                        text "文字颜色" xsize 220
                        textbutton "白":
                            action Function(_rb_sm_set, "_rb_sm_dialogue_color", "#FFFFFF")
                        textbutton "黄":
                            action Function(_rb_sm_set, "_rb_sm_dialogue_color", "#FFF2A8")
                        textbutton "青":
                            action Function(_rb_sm_set, "_rb_sm_dialogue_color", "#A8F0FF")

                    hbox:
                        spacing 8
                        text "文字描边：%s" % persistent._rb_sm_dialogue_outline xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_dialogue_outline", -1, 0, 8)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_dialogue_outline", 1, 0, 8)

                    text "选项框设置" size 20
                    hbox:
                        spacing 8
                        text "选项框模组" xsize 220
                        textbutton ("启用" if persistent._rb_sm_choice_enabled else "禁用"):
                            action Function(_rb_sm_toggle, "_rb_sm_choice_enabled")
                        text "关闭后恢复游戏原本的选项框样式" size 13

                    hbox:
                        spacing 8
                        text "选项文字大小：%s" % persistent._rb_sm_choice_size xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_choice_size", -1, 12, 75)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_choice_size", 1, 12, 75)

                    hbox:
                        spacing 8
                        text "选项宽度：%s" % persistent._rb_sm_choice_width xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_choice_width", -40, 400, 1920)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_choice_width", 40, 400, 1920)

                    hbox:
                        spacing 8
                        text "选项横向位置：%s" % persistent._rb_sm_choice_xoffset xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_choice_xoffset", -10, -960, 960)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_choice_xoffset", 10, -960, 960)

                    hbox:
                        spacing 8
                        text "选项纵向位置：%s" % persistent._rb_sm_choice_yoffset xsize 220
                        textbutton "-":
                            action Function(_rb_sm_step, "_rb_sm_choice_yoffset", -10, -960, 960)
                        textbutton "+":
                            action Function(_rb_sm_step, "_rb_sm_choice_yoffset", 10, -960, 960)

                    hbox:
                        spacing 8
                        text "选项对齐" xsize 220
                        textbutton "左":
                            action Function(_rb_sm_set, "_rb_sm_choice_align", "left")
                        textbutton "中":
                            action Function(_rb_sm_set, "_rb_sm_choice_align", "center")
                        textbutton "右":
                            action Function(_rb_sm_set, "_rb_sm_choice_align", "right")

                    hbox:
                        spacing 8
                        text "选项背景" xsize 220
                        textbutton ("显示" if persistent._rb_sm_choice_background else "隐藏"):
                            action Function(_rb_sm_toggle, "_rb_sm_choice_background")
                        textbutton "白":
                            action Function(_rb_sm_set, "_rb_sm_choice_color", "#FFFFFF")
                        textbutton "黄":
                            action Function(_rb_sm_set, "_rb_sm_choice_color", "#FFF2A8")
                        textbutton "青":
                            action Function(_rb_sm_set, "_rb_sm_choice_color", "#A8F0FF")

                    text "快捷菜单" size 20
                    hbox:
                        spacing 8
                        text "RenpyBox 快捷菜单" xsize 220
                        textbutton ("启用" if persistent._rb_sm_quick_menu_enabled else "禁用"):
                            action Function(_rb_sm_toggle, "_rb_sm_quick_menu_enabled")
                        text "启用后会隐藏游戏原 quick_menu" size 13

                    hbox:
                        spacing 8
                        textbutton ("返回：开" if persistent._rb_sm_quick_return else "返回：关"):
                            action Function(_rb_sm_toggle, "_rb_sm_quick_return")
                        textbutton ("历史：开" if persistent._rb_sm_quick_history else "历史：关"):
                            action Function(_rb_sm_toggle, "_rb_sm_quick_history")
                        textbutton ("隐藏：开" if persistent._rb_sm_quick_hide else "隐藏：关"):
                            action Function(_rb_sm_toggle, "_rb_sm_quick_hide")
                        textbutton ("跳过：开" if persistent._rb_sm_quick_skip else "跳过：关"):
                            action Function(_rb_sm_toggle, "_rb_sm_quick_skip")

                    hbox:
                        spacing 8
                        textbutton ("自动：开" if persistent._rb_sm_quick_auto else "自动：关"):
                            action Function(_rb_sm_toggle, "_rb_sm_quick_auto")
                        textbutton ("保存：开" if persistent._rb_sm_quick_save else "保存：关"):
                            action Function(_rb_sm_toggle, "_rb_sm_quick_save")
                        textbutton ("读取：开" if persistent._rb_sm_quick_load else "读取：关"):
                            action Function(_rb_sm_toggle, "_rb_sm_quick_load")
                        textbutton ("设置：开" if persistent._rb_sm_quick_preferences else "设置：关"):
                            action Function(_rb_sm_toggle, "_rb_sm_quick_preferences")

                    hbox:
                        spacing 8
                        textbutton ("快存：开" if persistent._rb_sm_quick_quicksave else "快存：关"):
                            action Function(_rb_sm_toggle, "_rb_sm_quick_quicksave")
                        textbutton ("快取：开" if persistent._rb_sm_quick_quickload else "快取：关"):
                            action Function(_rb_sm_toggle, "_rb_sm_quick_quickload")
                        textbutton "重置全部设置":
                            action Function(_rb_sm_reset)

screen _rb_simple_quick_menu():
    if persistent._rb_sm_quick_menu_enabled and not _rb_sm_is_main_menu():
        hbox:
            style_prefix "quick"
            xalign 0.5
            yalign 1.0

            if persistent._rb_sm_quick_return:
                textbutton "返回":
                    action Rollback()
            if persistent._rb_sm_quick_history:
                textbutton "历史":
                    action ShowMenu("history")
            if persistent._rb_sm_quick_hide:
                textbutton "隐藏":
                    action HideInterface()
            if persistent._rb_sm_quick_skip:
                textbutton "跳过":
                    action Skip() alternate Skip(fast=True, confirm=True)
            if persistent._rb_sm_quick_auto:
                textbutton "自动":
                    action Preference("auto-forward", "toggle")
            if persistent._rb_sm_quick_save:
                textbutton "保存":
                    action ShowMenu("save")
            if persistent._rb_sm_quick_load:
                textbutton "读取":
                    action ShowMenu("load")
            if persistent._rb_sm_quick_quicksave:
                textbutton "快存":
                    action QuickSave()
            if persistent._rb_sm_quick_quickload:
                textbutton "快取":
                    action QuickLoad()
            if persistent._rb_sm_quick_preferences:
                textbutton "设置":
                    action ShowMenu("preferences")
