## SOF

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
##
##    ┌──────┬────────────────────────────┬────────────┐
##    │ ZLZK │ Universal Gallery Unlocker │ 2024-01-24 │
##    └──────┴────────────────────────────┴────────────┘
##
##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## Hijacks
init 1400 python in _mods.ZLZK._base_:

    @init()
    def _():
        """ Reserved namespace. """

        # Make all labels to be seen.
        @CallablePatcher(renpy, 'seen_label')
        def hijack(func, *args, **kwargs):
            return True

        # Make all images to be seen.
        @CallablePatcher(renpy, 'seen_image')
        def hijack(func, *args, **kwargs):
            return True

        # Make all audios to be seen.
        @CallablePatcher(renpy, 'seen_audio')
        def hijack(func, *args, **kwargs):
            return True

        ##▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪

        # Make all images to be unlocked.
        @CallablePatcher(RPY_store._m1_00gallery__GalleryArbitraryCondition, 'check')
        def hijack(method, *args, **kwargs):
            return True

    ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

    @init()
    def _():
        """ Reserved namespace. """

        # Make all missing persistent variables to be True.
        @CallablePatcher(renpy.game.Persistent, '__getattr__')
        def hijack(func, inst, name):
            if name.startswith("dumuqiao"):
                return func(name)
            if not name.startswith("_"):
                return True
            return func(name)

        # Make all persistent variables to be True.
        @CallablePatcher(renpy.game.Persistent, '__getattribute__')
        def hijack(func, inst, name):
            if name.startswith("dumuqiao"):
                return func(name)
            if not name.startswith("_"):
                return UGU_fake_value(func(name))
            return func(name)

    ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

    # RPY "script reload" fix.

    @init()
    def _():
        """ Reserved namespace. """

        replaced = ZLZK_replaced_callables
        inserted = ZLZK_inserted_callables

        ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

        @CallablePatcher(renpy, 'utter_restart')
        def hijack(func, *args, **kwargs):
            while replaced:
                setattr( *replaced.pop() )
            while inserted:
                delattr( *inserted.pop() )
            return func(*args, **kwargs)
        del hijack

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## EOF