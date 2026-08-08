init 999 python:
    def _rb_show_urm_button():
        if globals().get("_rb_gallery_installed", False):
            return False
        urm = globals().get("x52URM")
        return urm is not None and hasattr(urm, "Open")

    if "_rb_urm_button" not in config.overlay_screens:
        config.overlay_screens.append("_rb_urm_button")

screen _rb_urm_button():
    zorder 100

    if _rb_show_urm_button():
        frame:
            xalign 0.98
            yalign 0.11
            xpadding 10
            ypadding 6

            vbox:
                spacing 4
                textbutton "修改器":
                    action x52URM.Open()
                text "快捷键：Alt+M" size 14
