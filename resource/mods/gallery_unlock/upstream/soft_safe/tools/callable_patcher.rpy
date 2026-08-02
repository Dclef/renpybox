## SOF

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
##
##    ┌──────┬──────────────────┬────────────┐
##    │ ZLZK │ Callable Patcher │ 2024-01-24 │
##    └──────┴──────────────────┴────────────┘
##
##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## Callable Patcher - Variables
init -1460 python in _mods.ZLZK._base_:

    ZLZK_replaced_callables = set( )
    ZLZK_inserted_callables = set( )

##▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪

## Callable Patcher
init -1460 python in _mods.ZLZK._base_:

    def CallablePatcher():
        """ Reserved namespace. """

        from types import ModuleType
        from types import FunctionType

        WrapperDescriptorType = type(object.__init__)

        ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

        def get_attribute(kind, obj, name):

            try:
                rv = getattr(obj, name)

            except AttributeError:
                if kind == "instace":
                    message = "'{}' object has no attribute '{}'".format(obj.__name__, name)
                elif kind == "class":
                    message = "type object '{}' has no attribute '{}'".format(obj.__name__, name)
                else:
                    message = "module '{}' has no attribute '{}'".format(obj.__name__, name)
                raise AttributeError(message)

            if not callable(rv):
                if kind == "instace":
                    message = "'{}' object attribute '{}' is not callable".format(obj.__name__, name)
                elif kind == "class":
                    message = "type object '{}' attribute '{}' is not callable".format(obj.__name__, name)
                else:
                    message = "module '{}' attribute '{}' is not callable".format(obj.__name__, name)
                raise TypeError(message)

            return rv

        ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

        def make_callable_wrapper(obj, hijack):

            @wraps( obj if hasattr(obj, '__name__') else obj.__class__ )
            def wrapper(*args, **kwargs):
                return hijack(obj, *args, **kwargs)

            return wrapper

        def make_staticmethod_wrapper(method, hijack):

            @wraps(method)
            def wrapper(*args, **kwargs):
                return hijack(method, *args, **kwargs)

            return staticmethod(wrapper)

        def make_classmethod_wrapper(method, hijack):

            @wraps(method)
            def wrapper(cls, *args, **kwargs):
                return hijack(method, cls, *args, **kwargs)

            return classmethod(wrapper)

        def make_instacemethod_wrapper(method, hijack):

            @wraps(method)
            def wrapper(self, *args, **kwargs):
                return hijack(method.__get__(self), self, *args, **kwargs)

            return wrapper

        ##▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪

        def patch_callable(obj, name, hijack, kind, raw_attr, obj_attr):

            if kind == "module":
                make_wrapper = make_callable_wrapper

            else: # class or instace
                raw_type = type(raw_attr)

                if raw_type is FunctionType: # instance-method
                    make_wrapper = make_instacemethod_wrapper

                elif raw_type is staticmethod:
                    make_wrapper = make_staticmethod_wrapper

                elif raw_type is classmethod:
                    make_wrapper = make_classmethod_wrapper

                elif raw_type is WrapperDescriptorType: # instance-method of object
                    make_wrapper = make_instacemethod_wrapper

                else: # callable-class
                    make_wrapper = make_callable_wrapper

            wrapper = make_wrapper(obj_attr, hijack)

            setattr(obj, name, wrapper)

        ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

        def CallablePatcher(obj, name, deep=True): # @Decorator
            """
                Monkey patches callable hijacks in callable owners.

                `obj`
                    Owner of callable attribute.
                    Can be instace, class, or module.

                `name`
                    Attribute name.

                `deep`
                    Deep patching.

                    When 'True' and possible, patches method-owner instead of callable-owner.

                `hijack`
                    Hijack function.
            """

            def callable_patcher(hijack):

                owner = type(obj)

                if owner is ModuleType:
                    kind = "module"
                elif owner is type:
                    kind = "class"
                else:
                    kind = "instace"

                if hasattr(obj, '__name__'):
                    owner = obj

                ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

                obj_attr = get_attribute(kind, owner, name)

                ##▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪

                if kind == "module":

                    raw_attr = vars(owner)[name]

                    sub = True

                else: # class or instace

                    owners = owner.mro()

                    if deep:
                        depth = len(owners) - 1
                    else:
                        depth = 1

                    for i, o in enumerate(owners):
                        raw_attr = vars(o).get(name, None)

                        if raw_attr is not None:
                            break

                    sub = i < depth

                    if sub:
                        owner = o

                ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

                patch_callable(owner, name, hijack, kind, raw_attr, obj_attr)

                ##▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪

                if sub:
                    ZLZK_replaced_callables.add( (owner, name, raw_attr) )
                else:
                    ZLZK_inserted_callables.add( (owner, name) )

            ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

            return callable_patcher

        ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

        return CallablePatcher

    ##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

    CallablePatcher = CallablePatcher()

##●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●

## EOF