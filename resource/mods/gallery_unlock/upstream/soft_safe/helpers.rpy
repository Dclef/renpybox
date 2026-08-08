## SOF

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
##
##    ┌──────┬────────────────────────────┬────────────┐
##    │ ZLZK │ Universal Gallery Unlocker │ 2024-01-24 │
##    └──────┴────────────────────────────┴────────────┘
##
##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## Helpers
init -1490 python in _mods.ZLZK._base_:

    def init(*args): # @Decorator
        """
            Unwraps a function or instantiates a class.

            `args`
                Arguments to be passed to `obj`.

            `obj`
                Function to be unwrapped,
                or class to be instantiated.
        """

        def init(obj):
            return obj(*args)

        return init

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## EOF