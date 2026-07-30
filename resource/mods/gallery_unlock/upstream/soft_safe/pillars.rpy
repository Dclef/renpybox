## SOF

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
##
##    ┌──────┬────────────────────────────┬────────────┐
##    │ ZLZK │ Universal Gallery Unlocker │ 2024-01-24 │
##    └──────┴────────────────────────────┴────────────┘
##
##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## Pillars
init -1470 python in _mods.ZLZK._base_:

    class FakeCond(object):

        if PY2:
            def __nonzero__(self):
                return True
        else:
            def __bool__(self):
                return True

        def __eq__(self, o):
            return bool(o)

        def __ne__(self, o):
            return not(o)

        def __contains__(self, _):
            return True

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## EOF