init 999:
    style namebox:
        background Solid("#00000000")
        xminimum 1
        yminimum 1

init python:
    def dumuqiao_control_original_quick_menu():
        if persistent.dumuqiao_29_qmod == 0:
            renpy.show_screen("quick_menu")
        else:
            renpy.hide_screen("quick_menu")
    config.interact_callbacks.append(dumuqiao_control_original_quick_menu)
    
    config.keymap['dumuqiao_ChoiceSettings'] = ['alt_K_9']

define config.overlay_screens = ["dumuqiao_choice_keymap", "dumuqiao_custom_quick_menu"]

screen dumuqiao_choice_keymap:
    key "alt_K_9" action ToggleScreen("dumuqiao_ChoiceSettings")

#--------------------- 持久化设置变量---------------------#
default persistent.dumuqiao_0_ce = True     
default persistent.dumuqiao_1_de = True       

default persistent.dumuqiao_2_ch1 = False
default persistent.dumuqiao_3_ch2 = False
default persistent.dumuqiao_4_ch3 = False
default persistent.dumuqiao_5_ch4 = False
default persistent.dumuqiao_6_ch5 = False

define dumuqiao_7_bgal_default = 0
define dumuqiao_8_cali_default = "center"
define dumuqiao_9_csiz_default = 30
define dumuqiao_10_csho_default = True
define dumuqiao_11_ctco_default = "#ffffff"
define dumuqiao_12_cwid_default = 1100
define dumuqiao_13_cxof_default = 0
define dumuqiao_14_cyof_default = 0
define dumuqiao_15_dsiz_default = 37
define dumuqiao_16_dtco_default = "#FFFFFF"
define dumuqiao_17_dwid_default = 1616
define dumuqiao_18_dxof_default = 0
define dumuqiao_19_dyof_default = 0
define dumuqiao_21_nsiz_default = 42
define dumuqiao_24_outs_default = 3

default persistent.dumuqiao_7_bgal = dumuqiao_7_bgal_default
default persistent.dumuqiao_8_cali = dumuqiao_8_cali_default
default persistent.dumuqiao_9_csiz = dumuqiao_9_csiz_default
default persistent.dumuqiao_10_csho = dumuqiao_10_csho_default
default persistent.dumuqiao_11_ctco = dumuqiao_11_ctco_default
default persistent.dumuqiao_12_cwid = dumuqiao_12_cwid_default
default persistent.dumuqiao_13_cxof = dumuqiao_13_cxof_default
default persistent.dumuqiao_14_cyof = dumuqiao_14_cyof_default
default persistent.dumuqiao_15_dsiz = dumuqiao_15_dsiz_default
default persistent.dumuqiao_16_dtco = dumuqiao_16_dtco_default
default persistent.dumuqiao_17_dwid = dumuqiao_17_dwid_default
default persistent.dumuqiao_18_dxof = dumuqiao_18_dxof_default
default persistent.dumuqiao_19_dyof = dumuqiao_19_dyof_default

default dumuqiao_20_name = "独木桥"
default persistent.dumuqiao_21_nsiz = dumuqiao_21_nsiz_default
default persistent.dumuqiao_22_nxof = 0
default persistent.dumuqiao_23_nyof = 0
default persistent.dumuqiao_24_outs = dumuqiao_24_outs_default

define dumuqiao_35_qsiz_default = 25
default persistent.dumuqiao_25_qaut = False
default persistent.dumuqiao_26_qhid = False
default persistent.dumuqiao_27_qhis = False
default persistent.dumuqiao_28_qlod = True
default persistent.dumuqiao_29_qmod = 1         
default persistent.dumuqiao_30_qpre = True
default persistent.dumuqiao_31_qqld = True
default persistent.dumuqiao_32_qqsv = True
default persistent.dumuqiao_33_qret = True
default persistent.dumuqiao_34_qsav = True
default persistent.dumuqiao_35_qsiz = dumuqiao_35_qsiz_default
default persistent.dumuqiao_36_qskp = True

default persistent.dumuqiao_37_visi = True

default current_section = None
define quick_menu = True

#--------------------- 名称更改功能 ---------------------#
label dumuqiao_change_mc_name:
    "当前主角名字: [dumuqiao_20_name]"
    
    $ new_name = renpy.input("请输入主角名字：", default=dumuqiao_20_name, length=12)
    $ new_name = new_name.strip()
    if new_name:
        $ dumuqiao_20_name = new_name
    
    "主角名字已修改为: [new_name]"
    
    $ renpy.restart_interaction()
    
    hide screen dumuqiao_ChoiceSettings
    show screen dumuqiao_ChoiceSettings
    return

#--------------------- 屏幕覆盖 ---------------------#
init 9998:
    if persistent.dumuqiao_1_de:
        screen say(who, what):
            style_prefix "say"

            window:
                id "window"
                background Transform(
                    ConditionSwitch(
                "renpy.loadable('gui/textbox.png')", "gui/textbox.png",
                "True", Null()
                ),
                xalign=0.5,
                yalign=1.0,
                alpha=persistent.dumuqiao_7_bgal
                )
                xoffset persistent.dumuqiao_18_dxof
                yoffset persistent.dumuqiao_19_dyof

                if who is not None:
                    window:
                        id "namebox"
                        style "namebox"
                        yoffset persistent.dumuqiao_23_nyof
                        xoffset persistent.dumuqiao_22_nxof
                        text who id "who" size persistent.dumuqiao_21_nsiz outlines [ (absolute(persistent.dumuqiao_24_outs), "#000", absolute(0), absolute(0)) ]

                text what id "what" size persistent.dumuqiao_15_dsiz outlines [ (absolute(persistent.dumuqiao_24_outs), "#000", absolute(0), absolute(0)) ] color persistent.dumuqiao_16_dtco xsize persistent.dumuqiao_17_dwid

    if persistent.dumuqiao_0_ce:
        screen choice(items):
            if persistent.dumuqiao_8_cali == "left":
                style_prefix "choice_left"
            elif persistent.dumuqiao_8_cali == "right":
                style_prefix "choice_right"
            else:
                style_prefix "choice"
            
            vbox:
                yalign 0.5
                xalign 0.5
                yoffset persistent.dumuqiao_14_cyof
                xoffset persistent.dumuqiao_13_cxof

                for i in items:
                    if persistent.dumuqiao_8_cali == "left":
                        $ text_xalign = 0.0
                        $ gui.choice_button_text_xalign = 0.0
                    elif persistent.dumuqiao_8_cali == "right":
                        $ text_xalign = 1.0
                        $ gui.choice_button_text_xalign = 1.0
                    else:
                        $ text_xalign = 0.5
                        $ gui.choice_button_text_xalign = 0.5
                    
                    textbutton i.caption:
                        action i.action
                        if persistent.dumuqiao_10_csho == False:
                            background None
                        text_size persistent.dumuqiao_9_csiz
                        xsize persistent.dumuqiao_12_cwid
                        text_xalign text_xalign
                        text_color persistent.dumuqiao_11_ctco

#--------------------- 自定义快速菜单 ---------------------#
screen dumuqiao_custom_quick_menu():
    variant ("small", "medium", "large")
    zorder 100
        
    if persistent.dumuqiao_29_qmod == 1:
        hbox:
            style_prefix "quick"
            xalign 0.5
            yalign 1.0
            
            if persistent.dumuqiao_33_qret:
                textbutton _("返回"):
                    text_size persistent.dumuqiao_35_qsiz
                    action Rollback()
            if persistent.dumuqiao_27_qhis:
                textbutton _("历史"):
                    text_size persistent.dumuqiao_35_qsiz
                    action ShowMenu('history')
            if persistent.dumuqiao_26_qhid:
                textbutton _("隐藏"):
                    text_size persistent.dumuqiao_35_qsiz
                    action HideInterface()
            if persistent.dumuqiao_36_qskp:
                textbutton _("跳过"):
                    text_size persistent.dumuqiao_35_qsiz
                    action Skip() alternate Skip(fast=True, confirm=True)
            if persistent.dumuqiao_25_qaut:
                textbutton _("自动"):
                    text_size persistent.dumuqiao_35_qsiz
                    action Preference("auto-forward", "toggle")
            if persistent.dumuqiao_34_qsav:
                textbutton _("保存"):
                    text_size persistent.dumuqiao_35_qsiz
                    action ShowMenu('save')
            if persistent.dumuqiao_28_qlod:
                textbutton _("读取"):
                    text_size persistent.dumuqiao_35_qsiz
                    action ShowMenu('load')
            if persistent.dumuqiao_32_qqsv:
                textbutton _("快存"):
                    text_size persistent.dumuqiao_35_qsiz
                    action QuickSave()
            if persistent.dumuqiao_31_qqld:
                textbutton _("快取"):
                    text_size persistent.dumuqiao_35_qsiz
                    action QuickLoad()
            if persistent.dumuqiao_30_qpre:
                textbutton _("设置"):
                    text_size persistent.dumuqiao_35_qsiz
                    action ShowMenu('preferences')
            textbutton _("模组"):
                text_size persistent.dumuqiao_35_qsiz
                action ToggleScreen("dumuqiao_ChoiceSettings")
        
        hbox:
            style_prefix "quick"
            xalign 0.0
            yalign 1.0
            
            if persistent.dumuqiao_2_ch1:
                textbutton _("作弊1"):
                    text_size persistent.dumuqiao_35_qsiz
                    action ShowMenu("cheatmenu")
            if persistent.dumuqiao_3_ch2:
                textbutton _("作弊2"):
                    text_size persistent.dumuqiao_35_qsiz
                    action ShowMenu("cheatmod")
            if persistent.dumuqiao_4_ch3:
                textbutton _("作弊3"):
                    text_size persistent.dumuqiao_35_qsiz
                    action ShowMenu("cheats")
            if persistent.dumuqiao_5_ch4:
                textbutton _("作弊4"):
                    text_size persistent.dumuqiao_35_qsiz
                    action ShowMenu("modmenu")
            if persistent.dumuqiao_6_ch5:
                textbutton _("作弊5"):
                    text_size persistent.dumuqiao_35_qsiz
                    action ShowMenu("bad75_cheat_menu")

#--------------------- 主设置界面 ---------------------#
screen dumuqiao_ChoiceSettings:
    modal True
    
    key "game_menu" action Hide("dumuqiao_ChoiceSettings")
    key "K_ESCAPE" action Hide("dumuqiao_ChoiceSettings")
    
    add Solid("#0000004D")
    
    frame:
        xalign 0.5
        yalign 0.5
        xpadding 30
        ypadding 30
        background Solid("#0000004D")
        
        vbox:
            spacing 10
            
            hbox:
                xalign 0.5
                spacing 50
                label _("独木桥模组6.27版本(快捷键Alt+9)") text_size 20
            
            viewport:
                scrollbars "vertical"
                mousewheel True
                xsize 1000
                ysize 750
                vscrollbar_xsize 50
                
                vbox:
                    spacing 15
                    xalign 0.5
                    
                    # ---------- 主角改名 ----------
                    frame:
                        background Solid("#00000000")
                        xfill True
                        padding (15, 15)
                        
                        vbox:
                            spacing 10
                            xalign 0.5
                            
                            textbutton "主角改名设置 ▼":
                                text_size 22
                                action SetVariable("current_section", 28 if current_section != 28 else None)
                                xalign 0.5
                            
                            if current_section == 28:
                                vbox:
                                    spacing 8
                                    xalign 0.5
                                    
                                    text _("当前主角名字: [dumuqiao_20_name]") size 18 xalign 0.5
                                    textbutton "修改主角名字":
                                        text_size 16
                                        action [
                                            Hide("dumuqiao_ChoiceSettings"),
                                            Call("dumuqiao_change_mc_name")
                                        ]
                                        xalign 0.5
                    
                    # ---------- 对话框设置 ----------
                    frame:
                        background Solid("#00000000")
                        xfill True
                        padding (15, 15)
                        
                        vbox:
                            spacing 10
                            xalign 0.5
                            
                            hbox:
                                xfill True
                                textbutton "重置":
                                    text_size 22
                                    action [
                                        SetField(persistent, "dumuqiao_23_nyof", 0),
                                        SetField(persistent, "dumuqiao_15_dsiz", dumuqiao_15_dsiz_default),
                                        SetField(persistent, "dumuqiao_21_nsiz", dumuqiao_21_nsiz_default),
                                        SetField(persistent, "dumuqiao_7_bgal", dumuqiao_7_bgal_default),
                                        SetField(persistent, "dumuqiao_18_dxof", dumuqiao_18_dxof_default),
                                        SetField(persistent, "dumuqiao_19_dyof", dumuqiao_19_dyof_default),
                                        SetField(persistent, "dumuqiao_22_nxof", 0),
                                        SetField(persistent, "dumuqiao_16_dtco", dumuqiao_16_dtco_default),
                                        SetField(persistent, "dumuqiao_17_dwid", dumuqiao_17_dwid_default)
                                    ]
                                    xalign 0.9
                                textbutton "对话框设置 ▼":
                                    text_size 22
                                    action SetVariable("current_section", 29 if current_section != 29 else None)
                                    xalign 0.0
                            
                            if current_section == 29:
                                vbox:
                                    spacing 8
                                    xalign 0.5
                                    
                                    hbox:
                                        spacing 15
                                        xalign 0.5
                                        text _("对话框模组:") size 18 yalign 0.5
                                        textbutton _("启用"):
                                            text_size 18
                                            yalign 0.5
                                            selected (persistent.dumuqiao_1_de == True)
                                            action [SetField(persistent, 'dumuqiao_1_de', True), Notify("已启用对话框模组，重启游戏后生效")]
                                        textbutton _("禁用"):
                                            text_size 18
                                            yalign 0.5
                                            selected (persistent.dumuqiao_1_de == False)
                                            action [SetField(persistent, 'dumuqiao_1_de', False), Notify("已禁用对话框模组，重启游戏后生效")]
                                    
                                    $ opacity_percent = int(persistent.dumuqiao_7_bgal * 100)
                                    vbox:
                                        spacing 5
                                        text _("背景透明度: [opacity_percent]%") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_7_bgal', range=1.0, step=0.01)
                                            xalign 0.5
                                    
                                    vbox:
                                        spacing 5
                                        text _("全局左右位置: [persistent.dumuqiao_18_dxof]") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_18_dxof', range=1920, offset=-960, step=1)
                                            xalign 0.5
                                    
                                    vbox:
                                        spacing 5
                                        text _("全局上下位置: [persistent.dumuqiao_19_dyof]") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_19_dyof', range=1920, offset=-960, step=1)
                                            xalign 0.5
                                    
                                    vbox:
                                        spacing 5
                                        text _("对话文字大小: [persistent.dumuqiao_15_dsiz]/75") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_15_dsiz', range=75, step=1)
                                            xalign 0.5

                                    vbox:
                                        spacing 5
                                        text _("对话文字长度: [persistent.dumuqiao_17_dwid]/1920") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_17_dwid', range=1920, offset=400, step=10)
                                            xalign 0.5
                             
                                    vbox:
                                        spacing 5
                                        text _("名字文字大小: [persistent.dumuqiao_21_nsiz]/75") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_21_nsiz', range=75, step=1)
                                            xalign 0.5
                                    
                                    vbox:
                                        spacing 5
                                        text _("名字上下位置: [persistent.dumuqiao_23_nyof]") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_23_nyof', range=1920, offset=-960, step=1)
                                            xalign 0.5
                                    
                                    vbox:
                                        spacing 5
                                        text _("名字左右位置: [persistent.dumuqiao_22_nxof]") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_22_nxof', range=1920, offset=-960, step=1)
                                            xalign 0.5
                                    
                                    vbox:
                                        spacing 5
                                        text _("文字描边粗细: [persistent.dumuqiao_24_outs]/10") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_24_outs', range=10, step=1)
                                            xalign 0.5
                                    
                                    hbox:
                                        spacing 15
                                        xalign 0.5
                                        text _("文字颜色:") size 18 yalign 0.5
                                        textbutton _("白色"):
                                            text_size 18
                                            yalign 0.5
                                            text_color "#FFFFFF"
                                            selected (persistent.dumuqiao_16_dtco == "#FFFFFF")
                                            action SetField(persistent, "dumuqiao_16_dtco", "#FFFFFF")
                                        textbutton _("红色"):
                                            text_size 18
                                            yalign 0.5
                                            text_color "#FF0000"
                                            selected (persistent.dumuqiao_16_dtco == "#FF0000")
                                            action SetField(persistent, "dumuqiao_16_dtco", "#FF0000")
                                        textbutton _("粉色"):
                                            text_size 18
                                            yalign 0.5
                                            text_color "#F61EEC"
                                            selected (persistent.dumuqiao_16_dtco == "#F61EEC")
                                            action SetField(persistent, "dumuqiao_16_dtco", "#F61EEC")
                                        textbutton _("黄色"):
                                            text_size 18
                                            yalign 0.5
                                            text_color "#FFFF00"
                                            selected (persistent.dumuqiao_16_dtco == "#FFFF00")
                                            action SetField(persistent, "dumuqiao_16_dtco", "#FFFF00")
                    
                    # ---------- 选项框设置 ----------
                    frame:
                        background Solid("#00000000")
                        xfill True
                        padding (15, 15)
                        
                        vbox:
                            spacing 10
                            xalign 0.5
                            
                            hbox:
                                xfill True
                                textbutton "重置":
                                    text_size 22
                                    action [
                                        SetField(persistent, "dumuqiao_13_cxof", 0),
                                        SetField(persistent, "dumuqiao_9_csiz", dumuqiao_9_csiz_default),
                                        SetField(persistent, "dumuqiao_14_cyof", dumuqiao_14_cyof_default),
                                        SetField(persistent, "dumuqiao_12_cwid", dumuqiao_12_cwid_default),
                                        SetField(persistent, "dumuqiao_24_outs", dumuqiao_24_outs_default),
                                        SetField(persistent, "dumuqiao_10_csho", dumuqiao_10_csho_default),
                                        SetField(persistent, "dumuqiao_8_cali", dumuqiao_8_cali_default),
                                        SetField(persistent, "dumuqiao_11_ctco", dumuqiao_11_ctco_default)
                                    ]
                                    xalign 0.9
                                textbutton "选项框设置 ▼":
                                    text_size 22
                                    action SetVariable("current_section", 30 if current_section != 30 else None)
                                    xalign 0.0
                            
                            if current_section == 30:
                                vbox:
                                    spacing 8
                                    xalign 0.5
                                    
                                    text _(" 在游戏安装作弊功能后没有生效，比如选项高亮，好感加成") size 15 yalign 0.5 color "#ff9900"
                                    text _("没出现那么就禁用功能。开启后可以修改选项框，默认禁用") size 15 xalign 0.5 color "#ff9900"
                                    
                                    hbox:
                                        spacing 15
                                        xalign 0.5
                                        textbutton _("启用"):
                                            text_size 18
                                            yalign 0.5
                                            selected (persistent.dumuqiao_0_ce == True)
                                            action [SetField(persistent, 'dumuqiao_0_ce', True), Notify("已启用自定义选项框，重启游戏后生效")]
                                        textbutton _("禁用"):
                                            text_size 18
                                            yalign 0.5
                                            selected (persistent.dumuqiao_0_ce == False)
                                            action [SetField(persistent, 'dumuqiao_0_ce', False), Notify("已禁用自定义选项框，重启游戏后生效")]
                                    
                                    vbox:
                                        spacing 5
                                        text _("上下位置: [persistent.dumuqiao_14_cyof]") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_14_cyof', range=1920, offset=-960, step=1)
                                            xalign 0.5
                                    
                                    vbox:
                                        spacing 5
                                        text _("左右位置: [persistent.dumuqiao_13_cxof]") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_13_cxof', range=1920, offset=-960, step=1)
                                            xalign 0.5
                                    
                                    vbox:
                                        spacing 5
                                        text _("按钮宽度: [persistent.dumuqiao_12_cwid]") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_12_cwid', range=1800, step=1)
                                            xalign 0.5
                                    
                                    vbox:
                                        spacing 5
                                        text _("文字大小: [persistent.dumuqiao_9_csiz]/75") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_9_csiz', range=75, step=1)
                                            xalign 0.5
                                    
                                    hbox:
                                        spacing 15
                                        xalign 0.5
                                        text _("文字颜色:") size 18 yalign 0.5
                                        textbutton _("白色"):
                                            text_size 18
                                            yalign 0.5
                                            text_color "#FFFFFF"
                                            selected (persistent.dumuqiao_11_ctco == "#FFFFFF")
                                            action SetField(persistent, "dumuqiao_11_ctco", "#FFFFFF")
                                        textbutton _("红色"):
                                            text_size 18
                                            yalign 0.5
                                            text_color "#FF0000"
                                            selected (persistent.dumuqiao_11_ctco == "#FF0000")
                                            action SetField(persistent, "dumuqiao_11_ctco", "#FF0000")
                                        textbutton _("粉色"):
                                            text_size 18
                                            yalign 0.5
                                            text_color "#F61EEC"
                                            selected (persistent.dumuqiao_11_ctco == "#F61EEC")
                                            action SetField(persistent, "dumuqiao_11_ctco", "#F61EEC")
                                        textbutton _("黄色"):
                                            text_size 18
                                            yalign 0.5
                                            text_color "#FFFF00"
                                            selected (persistent.dumuqiao_11_ctco == "#FFFF00")
                                            action SetField(persistent, "dumuqiao_11_ctco", "#FFFF00")
                                    
                                    hbox:
                                        spacing 20
                                        xalign 0.5
                                        text _("背景:") size 18 yalign 0.5
                                        if persistent.dumuqiao_10_csho == False:
                                            textbutton _("关"):
                                                text_size 18
                                                action SetField(persistent, "dumuqiao_10_csho", True)
                                        else:
                                            textbutton _("开"):
                                                text_size 18
                                                action SetField(persistent, "dumuqiao_10_csho", False)
                                    
                                    hbox:
                                        spacing 20
                                        xalign 0.5
                                        text _("对齐:") size 18 yalign 0.5
                                        textbutton _("左"):
                                            text_size 18
                                            selected (persistent.dumuqiao_8_cali == "left")
                                            action SetField(persistent, "dumuqiao_8_cali", "left")
                                        textbutton _("中"):
                                            text_size 18
                                            selected (persistent.dumuqiao_8_cali == "center")
                                            action SetField(persistent, "dumuqiao_8_cali", "center")
                                        textbutton _("右"):
                                            text_size 18
                                            selected (persistent.dumuqiao_8_cali == "right")
                                            action SetField(persistent, "dumuqiao_8_cali", "right")
                    
                    # ---------- 快速菜单设置 ----------
                    frame:
                        background Solid("#00000000")
                        xfill True
                        padding (15, 15)
                        
                        vbox:
                            spacing 10
                            xalign 0.5
                            
                            hbox:
                                xfill True
                                textbutton "重置":
                                    text_size 22
                                    action [
                                        SetField(persistent, "dumuqiao_35_qsiz", dumuqiao_35_qsiz_default),
                                        SetField(persistent, "dumuqiao_29_qmod", 1)
                                    ]
                                    xalign 0.9
                                textbutton "各种菜单设置 ▼":
                                    text_size 22
                                    action SetVariable("current_section", 31 if current_section != 31 else None)
                                    xalign 0.0
                            
                            if current_section == 31:
                                vbox:
                                    spacing 8
                                    xalign 0.5
                                    
                                    vbox:
                                        spacing 5
                                        text _("文字大小: [persistent.dumuqiao_35_qsiz]/40") size 18 xalign 0.5
                                        bar:
                                            xsize 400
                                            ysize 25
                                            value FieldValue(persistent, 'dumuqiao_35_qsiz', range=40, step=1)
                                            xalign 0.5
                                    
                                    hbox:
                                        spacing 20
                                        xalign 0.5
                                        text _("显示模式:") size 18 yalign 0.5
                                        textbutton _("模组菜单"):
                                            text_size 18
                                            yalign 0.5
                                            selected (persistent.dumuqiao_29_qmod == 1)
                                            action SetField(persistent, "dumuqiao_29_qmod", 1)
                                        textbutton _("原版菜单"):
                                            text_size 18
                                            yalign 0.5
                                            selected (persistent.dumuqiao_29_qmod == 0)
                                            action SetField(persistent, "dumuqiao_29_qmod", 0)
                                        textbutton _("全部隐藏"):
                                            text_size 18
                                            yalign 0.5
                                            selected (persistent.dumuqiao_29_qmod == 2)
                                            action SetField(persistent, "dumuqiao_29_qmod", 2)
                                    
                                    hbox:
                                        spacing 20
                                        xalign 0.5
                                        text _("模组按钮:") size 18 yalign 0.5
                                        textbutton _("模组显示"):
                                            text_size 18
                                            yalign 0.5
                                            selected (persistent.dumuqiao_37_visi == True)
                                            action SetField(persistent, "dumuqiao_37_visi", True)
                                        textbutton _("模组隐藏"):
                                            text_size 18
                                            yalign 0.5
                                            selected (persistent.dumuqiao_37_visi == False)
                                            action SetField(persistent, "dumuqiao_37_visi", False)
                                        textbutton _("发布地址"):
                                            text_size 18
                                            yalign 0.5
                                            action OpenURL("https://open.vlinkx.cn/独木桥")
                    
                    # ---------- 菜单按钮设置 ----------
                    frame:
                        background Solid("#00000000")
                        xfill True
                        padding (15, 15)
                        
                        vbox:
                            spacing 10
                            xalign 0.5
                            
                            hbox:
                                xfill True
                                textbutton "重置":
                                    text_size 22
                                    action [
                                        SetField(persistent, "dumuqiao_33_qret", True),
                                        SetField(persistent, "dumuqiao_36_qskp", True),
                                        SetField(persistent, "dumuqiao_25_qaut", False),
                                        SetField(persistent, "dumuqiao_34_qsav", True),
                                        SetField(persistent, "dumuqiao_28_qlod", True),
                                        SetField(persistent, "dumuqiao_32_qqsv", True),
                                        SetField(persistent, "dumuqiao_31_qqld", True),
                                        SetField(persistent, "dumuqiao_30_qpre", True)
                                    ]
                                    xalign 0.9
                                textbutton "菜单按钮设置 ▼":
                                    text_size 22
                                    action SetVariable("current_section", 32 if current_section != 32 else None)
                                    xalign 0.0
                            
                            if current_section == 32:
                                vbox:
                                    spacing 10
                                    xalign 0.5
                                    
                                    hbox:
                                        spacing 15
                                        xalign 0.5
                                        textbutton "返回: {0}".format("开" if persistent.dumuqiao_33_qret else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_33_qret")
                                            xsize 100
                                        textbutton "历史: {0}".format("开" if persistent.dumuqiao_27_qhis else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_27_qhis")
                                            xsize 100
                                        textbutton "隐藏: {0}".format("开" if persistent.dumuqiao_26_qhid else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_26_qhid")
                                            xsize 100
                                    
                                    hbox:
                                        spacing 15
                                        xalign 0.5                                
                                        textbutton "跳过: {0}".format("开" if persistent.dumuqiao_36_qskp else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_36_qskp")
                                            xsize 100
                                        textbutton "自动: {0}".format("开" if persistent.dumuqiao_25_qaut else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_25_qaut")
                                            xsize 100
                                        textbutton "保存: {0}".format("开" if persistent.dumuqiao_34_qsav else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_34_qsav")
                                            xsize 100
                                    
                                    hbox:
                                        spacing 15
                                        xalign 0.5
                                        textbutton "读取: {0}".format("开" if persistent.dumuqiao_28_qlod else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_28_qlod")
                                            xsize 100
                                        textbutton "快存: {0}".format("开" if persistent.dumuqiao_32_qqsv else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_32_qqsv")
                                            xsize 100
                                        textbutton "快取: {0}".format("开" if persistent.dumuqiao_31_qqld else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_31_qqld")
                                            xsize 100
                                    
                                    hbox:
                                        spacing 15
                                        xalign 0.5                                
                                        textbutton "设置: {0}".format("开" if persistent.dumuqiao_30_qpre else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_30_qpre")
                                            xsize 100
                    
                    # ---------- 作弊按钮设置 ----------
                    frame:
                        background Solid("#00000000")
                        xfill True
                        padding (15, 15)
                        
                        vbox:
                            spacing 10
                            xalign 0.5
                            
                            hbox:
                                xfill True
                                textbutton "重置":
                                    text_size 22
                                    action [
                                        SetField(persistent, "dumuqiao_2_ch1", False),
                                        SetField(persistent, "dumuqiao_3_ch2", False),
                                        SetField(persistent, "dumuqiao_4_ch3", False),
                                        SetField(persistent, "dumuqiao_5_ch4", False),
                                        SetField(persistent, "dumuqiao_6_ch5", False)
                                    ]
                                    xalign 0.9
                                textbutton "作弊按钮设置 ▼":
                                    text_size 22
                                    action SetVariable("current_section", 33 if current_section != 33 else None)
                                    xalign 0.0
                            
                            if current_section == 33:
                                vbox:
                                    spacing 10
                                    xalign 0.5
                                    
                                    text _("开启后会在快速菜单显示作弊按钮") size 18 xalign 0.5 color "#ff9900"
                                    text _("需要游戏内有对应的作弊功能才能使用") size 16 xalign 0.5 color "#ff9900"
                                    
                                    hbox:
                                        spacing 15
                                        xalign 0.5
                                        textbutton "作弊1: {0}".format("开" if persistent.dumuqiao_2_ch1 else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_2_ch1")
                                            xsize 100
                                            tooltip "显示/隐藏作弊1按钮"
                                        textbutton "作弊2: {0}".format("开" if persistent.dumuqiao_3_ch2 else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_3_ch2")
                                            xsize 100
                                            tooltip "显示/隐藏作弊2按钮"
                                        textbutton "作弊3: {0}".format("开" if persistent.dumuqiao_4_ch3 else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_4_ch3")
                                            xsize 100
                                            tooltip "显示/隐藏作弊3按钮"
                                    
                                    hbox:
                                        spacing 15
                                        xalign 0.5
                                        textbutton "作弊4: {0}".format("开" if persistent.dumuqiao_5_ch4 else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_5_ch4")
                                            xsize 100
                                            tooltip "显示/隐藏作弊4按钮" 
                                        textbutton "作弊5: {0}".format("开" if persistent.dumuqiao_6_ch5 else "关"):
                                            text_size 18
                                            action ToggleField(persistent, "dumuqiao_6_ch5")
                                            xsize 100
                                            tooltip "显示/隐藏作弊5按钮"
                    
                    # ---------- 底部按钮 ----------
                    hbox:
                        spacing 20
                        xalign 0.5
                        
                        textbutton _("重置所有"):
                            text_size 18
                            action [
                                SetField(persistent, "dumuqiao_29_qmod", 1),
                                SetField(persistent, "dumuqiao_23_nyof", 0),
                                SetField(persistent, "dumuqiao_13_cxof", 0),
                                SetField(persistent, "dumuqiao_22_nxof", 0),
                                SetField(persistent, "dumuqiao_33_qret", True),
                                SetField(persistent, "dumuqiao_36_qskp", True),
                                SetField(persistent, "dumuqiao_25_qaut", False),
                                SetField(persistent, "dumuqiao_34_qsav", True),
                                SetField(persistent, "dumuqiao_28_qlod", True),
                                SetField(persistent, "dumuqiao_32_qqsv", True),
                                SetField(persistent, "dumuqiao_31_qqld", True),
                                SetField(persistent, "dumuqiao_30_qpre", True),
                                SetField(persistent, "dumuqiao_2_ch1", False),
                                SetField(persistent, "dumuqiao_3_ch2", False),
                                SetField(persistent, "dumuqiao_4_ch3", False),
                                SetField(persistent, "dumuqiao_5_ch4", False),
                                SetField(persistent, "dumuqiao_6_ch5", False),
                                SetVariable("current_section", None),
                                SetField(persistent, "dumuqiao_15_dsiz", dumuqiao_15_dsiz_default),
                                SetField(persistent, "dumuqiao_21_nsiz", dumuqiao_21_nsiz_default),
                                SetField(persistent, "dumuqiao_7_bgal", dumuqiao_7_bgal_default),
                                SetField(persistent, "dumuqiao_18_dxof", dumuqiao_18_dxof_default),
                                SetField(persistent, "dumuqiao_19_dyof", dumuqiao_19_dyof_default),
                                SetField(persistent, "dumuqiao_24_outs", dumuqiao_24_outs_default),
                                SetField(persistent, "dumuqiao_9_csiz", dumuqiao_9_csiz_default),
                                SetField(persistent, "dumuqiao_14_cyof", dumuqiao_14_cyof_default),
                                SetField(persistent, "dumuqiao_12_cwid", dumuqiao_12_cwid_default),
                                SetField(persistent, "dumuqiao_10_csho", dumuqiao_10_csho_default),
                                SetField(persistent, "dumuqiao_8_cali", dumuqiao_8_cali_default),
                                SetField(persistent, "dumuqiao_35_qsiz", dumuqiao_35_qsiz_default),
                                SetField(persistent, "dumuqiao_17_dwid", dumuqiao_17_dwid_default),
                                SetField(persistent, "dumuqiao_11_ctco", dumuqiao_11_ctco_default),
                                SetField(persistent, "dumuqiao_16_dtco", dumuqiao_16_dtco_default)
                            ]

                        textbutton _("更新地址"):
                            text_size 18
                            action OpenURL("https://open.vlinkx.cn/dumuqiao")

                        textbutton _("关闭模组"):
                            text_size 18
                            action Hide("dumuqiao_ChoiceSettings")

#--------------------- 悬浮模组按钮 ---------------------#
screen dumuqiao_simple_mod_button():
    zorder 1000
    modal False
    
    if persistent.dumuqiao_37_visi and not main_menu:
        button:
            xpos 220  
            ypos 10
            xsize 80
            ysize 40
            background Solid("#00000000")  
            hover_background Solid("#555555CC")
            action ToggleScreen("dumuqiao_ChoiceSettings")
            
            text "模组":
                color "#f80a34"
                size 20
                align (0.5, 0.5)

init python:
    config.overlay_screens.append("dumuqiao_simple_mod_button")