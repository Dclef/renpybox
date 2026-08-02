## SOF

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
##
##    ┌──────┬────────────────────────────┬────────────┐
##    │ ZLZK │ Universal Gallery Unlocker │ 2024-01-24 │
##    └──────┴────────────────────────────┴────────────┘
##
##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## Dynamic Code
init -1460 python in _mods.ZLZK._base_:

    @init()
    def UGU_fake_value():
        """ Reserved namespace. """

        def c(o):

            if o is False:
                return True

            if o is 0:
                return 1

            if o is "":
                return " "

            if isinstance(o, (set, list, tuple)):
                return o.__class__( c(v) for v in o )

            if isinstance(o, dict):
                return o.__class__( (k, c(v)) for (k, v) in o.items() )

            return o

        ##▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪

        def f(*args):
            return True

        ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

        def UGU_fake_value(o):

            if isinstance(o, (set, list, dict)):
                o = type(o.__class__.__name__, (o.__class__,), dict(__contains__=f))(o)

            return c(o)

        ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

        try:
            return UGU_fake_value
        finally:
            del UGU_fake_value

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## EOF