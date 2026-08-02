## SOF

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
##
##    ┌──────┬────────────────────────────┬────────────┐
##    │ ZLZK │ Universal Gallery Unlocker │ 2024-01-24 │
##    └──────┴────────────────────────────┴────────────┘
##
##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## Patterns
init -1470 python in _mods.ZLZK._base_:

    class UGU_REO(object):
        """ Collection of regex objects. """

        @init()
        def Varname():
            """ Reserved namespace. """

            # This matches varnames.
            P = re.compile(r"""(?x)

                # (any quote)
                (?:(?<!\\)(?:"{3}|'{3}|"|'))
            |
                # varnames (variable & attribute names)
                (?:
                    # (start of name)
                    \b

                    # (name)
                    persistent

                    # (dot)
                    \s*\.\s*

                    # (attribute name)
                    [a-zA-Z_]\w*

                    # (end of name)
                    \b
                )

            """)

            ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

            @init()
            class Varname(object):

                def __init__(self):
                    self.q = None

                ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

                def __call__(self, m):

                    m = m.group(0)

                    if not self.q:
                        if m[0] not in "\"'":
                            m = "fake"
                        else:
                            self.q = m

                    elif self.q == m:
                        self.q = None

                    return m

                ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

                def sub(self, *args, **kwargs):
                    """ ... """

                    self.__init__()

                    try:
                        return P.sub(self, *args)

                    finally:
                        self.__init__() # Clearing variables.

            ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

            try:
                return Varname
            finally:
                del Varname

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## EOF