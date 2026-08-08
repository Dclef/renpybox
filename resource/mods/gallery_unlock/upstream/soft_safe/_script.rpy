## SOF

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
##
##    ┌──────┬────────────────────────────┬────────────┐
##    │ ZLZK │ Universal Gallery Unlocker │ 2024-01-24 │
##    └──────┴────────────────────────────┴────────────┘
##
##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## Universal Gallery Unlocker
init 1400 python in _mods.ZLZK._base_:

    @init()
    def _():

        @init()
        def cond():
            """ Reserved namespace. """

            If = (renpy.sl2.slast.SLIf, renpy.sl2.slast.SLShowIf)

            ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

            def cond(n):
                """ Returns 'True' if `n` is 'if'/'showif', or 'False' otherwise. """

                return isinstance(n, If)

            ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

            try:
                return cond
            finally:
                del cond

        ##▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪

        @init()
        def func():
            """ Reserved namespace. """

            REV = UGU_REO.Varname

            D = { 'fake': FakeCond() }

            ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

            def func(n):
                """ Changes conditions with persistent variables. """

                e = n.entries

                for i, (s, o) in enumerate(e):

                    if s is None:
                        break

                    ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

                    c = REV.sub(s)

                    if c != s:

                        try:
                            c = eval(c, D)
                            c = bool(c)
                            c = RPY_str(c)

                        except Exception:
                            continue

                        e[i] = (c, o)

            ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

            try:
                return func
            finally:
                del func

        ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

        all_screens = renpy.display.screen.screens.values()
        target_screens = [s for s in all_screens if not s.name[0].startswith('dumuqiao')]
        ScreenPatcher(target_screens, cond, func)
##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## EOF