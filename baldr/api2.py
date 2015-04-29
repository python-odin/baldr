import six


def route(func, method, response, resource=None, path=None):
    assert response in ('list', 'detail', 'action')

    if not isinstance(method, (list, tuple)):
        method = (method,)
    func._route = (method, response, resource, path)


class ResourceApiMeta(type):
    def __new__(cls, name, bases, attrs):
        super_new = super(ResourceApiMeta, cls).__new__

        # attrs will never be empty for classes declared in the standard way
        # (ie. with the `class` keyword). This is quite robust.
        if name == 'NewBase' and attrs == {}:
            return super_new(cls, name, bases, attrs)

        parents = [b for b in bases if isinstance(b, ResourceApiBase) and not (b.__name__ == 'NewBase'
                                                                               and b.__mro__ == (b, object))]
        if not parents:
            # If this isn't a subclass of don't do anything special.
            return super_new(cls, name, bases, attrs)

        # Get list of routes
        routes = []
        for name, obj in attrs.items():
            if callable(obj) and hasattr(obj, '_route'):
                routes.append(obj._route)

        attrs['_routes'] = routes
        return super_new(cls, name, bases, attrs)


class ResourceApiBase(object):
    pass


class ResourceApi(six.with_metaclass(ResourceApiMeta, ResourceApiBase)):
    pass
