## SOF

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
##
##    ┌──────┬────────────────┬────────────┐
##    │ ZLZK │ Screen Patcher │ 2024-01-24 │
##    └──────┴────────────────┴────────────┘
##
##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## Screen Patcher
init -1460 python in _mods.ZLZK._base_:

    class ScreenPatcher(object):
        """
            Alters existing screens.

            Works only in init-phase.

            `screens`
                Screens to alter.
                Can be name/Screen, or sequence of name/Screen items.
        """

        __slots__ = ('cond', 'func')

        def __init__(self):
            self.cond = None
            self.func = None

        ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

        def __call__(self, screens, cond, func):

            self.cond = cond
            self.func = func

            Screen = renpy.display.screen.Screen
            screen = renpy.display.screen.get_screen_variant

            ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

            if isinstance(screens, (basestring, Screen)):
                screens = [screens]

            try:
                for s in screens:

                    if isinstance(s, basestring):
                        s = screen(s)

                    elif not isinstance(s, Screen):
                        raise TypeError("'{}' object received '{}' object".format(self.__class__.__name__, type(s).__name__))

                    self.B(s.ast)

            finally:
                self.__init__() # Resetting instance.

        ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

        def C(self, n):

            b = n.block

            if not b:
                return

            self.B(b)

        def I(self, n):

            e = n.entries

            if not e:
                return

            for _, b in e:
                self.B(b)

        def B(self, n):

            c = n.children

            if not c:
                return

            for d in c:
                self.D(d)

        ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

        def D(self, n):

            if self.cond(n):
                self.func(n)

            ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

            if hasattr(n, 'block'):
                self.C(n)

            elif hasattr(n, 'entries'):
                self.I(n)

            ##▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪

            if hasattr(n, 'children'):
                self.B(n)

    ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

    ScreenPatcher = ScreenPatcher()

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## EOF