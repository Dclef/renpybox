default persistent._rb_gallery_unlocked = False

init -1100 python:
    try:
        _rb_text_types = (str, unicode)
    except NameError:
        _rb_text_types = (str,)

    try:
        _rb_int_types = (int, long)
    except NameError:
        _rb_int_types = (int,)

init -1000 python:
    import renpy as _rb_renpy

    _rb_gallery_hijacked = []
    _rb_gallery_installed = False

    def _rb_is_protected_name(name):
        return isinstance(name, _rb_text_types) and (
            name.startswith("_")
            or name.startswith("dumuqiao")
            or name == "URMSettings"
        )

    def _rb_unlocked():
        try:
            persistent_map = _rb_renpy.game.persistent.__dict__
            return bool(persistent_map.get("_rb_gallery_unlocked", False))
        except Exception:
            return False

    def _rb_has_urm():
        try:
            urm = globals().get("x52URM")
            return urm is not None and hasattr(urm, "Open")
        except Exception:
            return False

    def _rb_has_simple_modifier():
        return bool(globals().get("_rb_simple_modifier_available", False))

    def _rb_swap_one(value):
        if isinstance(value, bool):
            return True if value is False else value

        if isinstance(value, _rb_int_types) and value == 0:
            return 1

        if isinstance(value, _rb_text_types) and value == "":
            return " "

        if isinstance(value, (set, list, tuple)):
            return value.__class__(_rb_swap_one(item) for item in value)

        if isinstance(value, dict):
            return value.__class__(
                (key, _rb_swap_one(item)) for (key, item) in value.items()
            )

        return value

    def _rb_contains_true(container):
        def contains(_self, _item):
            return True

        container_type = type(
            container.__class__.__name__,
            (container.__class__,),
            {"__contains__": contains},
        )
        return container_type(container)

    def _rb_swap(value):
        swapped = _rb_swap_one(value)
        if isinstance(swapped, (set, list, dict)):
            return _rb_contains_true(swapped)
        return swapped

    def _rb_hook(obj, name, wrapper_builder):
        original = getattr(obj, name)
        _rb_gallery_hijacked.append((obj, name, original))

        wrapper = wrapper_builder(original)
        try:
            wrapper.__name__ = original.__name__
            wrapper.__doc__ = original.__doc__
        except Exception:
            pass

        setattr(obj, name, wrapper)

    def _rb_unhook_hijacks():
        global _rb_gallery_installed
        while _rb_gallery_hijacked:
            setattr(*_rb_gallery_hijacked.pop())
        _rb_gallery_installed = False

    def _rb_wrap_seen(original):
        def wrapper(*args, **kwargs):
            if _rb_unlocked():
                return True
            return original(*args, **kwargs)

        return wrapper

    def _rb_wrap_getattr(original):
        def wrapper(self, name):
            if _rb_is_protected_name(name):
                return original(self, name)
            if _rb_unlocked():
                return True
            return original(self, name)

        return wrapper

    def _rb_wrap_getattribute(original):
        def wrapper(self, name):
            if _rb_is_protected_name(name):
                return original(self, name)
            if not _rb_unlocked():
                return original(self, name)
            return _rb_swap(original(self, name))

        return wrapper

    def _rb_wrap_restart(original):
        def wrapper(*args, **kwargs):
            _rb_unhook_hijacks()
            return original(*args, **kwargs)

        return wrapper

    def _rb_install_hijacks():
        global _rb_gallery_installed
        if _rb_gallery_installed:
            return

        _rb_gallery_installed = True
        _rb_hook(_rb_renpy.exports, "seen_label", _rb_wrap_seen)
        _rb_hook(_rb_renpy.exports, "seen_image", _rb_wrap_seen)
        _rb_hook(_rb_renpy.exports, "seen_audio", _rb_wrap_seen)
        _rb_hook(_rb_renpy.game.Persistent, "__getattr__", _rb_wrap_getattr)
        _rb_hook(_rb_renpy.game.Persistent, "__getattribute__", _rb_wrap_getattribute)
        _rb_hook(_rb_renpy.exports, "utter_restart", _rb_wrap_restart)

init 999 python:
    if "_rb_gallery_toggle" not in config.overlay_screens:
        config.overlay_screens.append("_rb_gallery_toggle")

init 1000 python:
    _rb_install_hijacks()

screen _rb_gallery_toggle():
    zorder 100
    key "K_F9" action ToggleScreen("_rb_game_tools")
    key "K_F10" action ToggleField(persistent, "_rb_gallery_unlocked")

    frame:
        xalign 0.98
        yalign 0.02
        xpadding 10
        ypadding 6

        textbutton "MOD":
            action ToggleScreen("_rb_game_tools")

screen _rb_game_tools():
    zorder 101
    modal True
    key "K_F9" action Hide("_rb_game_tools")
    key "K_F10" action ToggleField(persistent, "_rb_gallery_unlocked")

    frame:
        xalign 0.98
        yalign 0.09
        xsize 360
        xpadding 16
        ypadding 14

        vbox:
            spacing 10

            hbox:
                xfill True
                text "游戏工具" size 24
                null width 20
                textbutton "关闭":
                    action Hide("_rb_game_tools")

            text (
                "画廊全解锁：（开）"
                if persistent._rb_gallery_unlocked
                else "画廊全解锁：（关）"
            ) size 16

            textbutton (
                "恢复游戏原本的画廊进度"
                if persistent._rb_gallery_unlocked
                else "开启全部画廊"
            ):
                action ToggleField(persistent, "_rb_gallery_unlocked")

            if persistent._rb_gallery_unlocked:
                text "开启期间会绕过部分游戏判定，看完请关闭" size 14

            if _rb_has_urm():
                textbutton "打开修改器":
                    action x52URM.Open()

            if _rb_has_simple_modifier():
                textbutton "内置修改器":
                    action [
                        Hide("_rb_game_tools"),
                        Show("_rb_simple_modifier"),
                    ]

            text "F9：关闭面板    F10：切换画廊状态" size 14
