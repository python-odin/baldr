from __future__ import absolute_import
import six
from . import content_type_resolvers
from .api import CODECS


GET = 'GET'
POST = 'POST'
PUT = 'PUT'
DELETE = 'DELETE'

LIST = 'list'
DETAIL = 'detail'
ACTION = 'action'
PROCESSES = (LIST, DETAIL, ACTION)


def route(func, method, process, path=None, resource=None):
    """
    Decorator for defining a route.

    :param func:
    :param method:
    :param process:
    :param path:
    :param resource:

    """
    assert process in PROCESSES

    if isinstance(method, six.string_types):
        method = (method,)

    assert all(isinstance(m, six.string_types) for m in method)

    func._route = (method, process, path, resource)
    return func


def get_list(func, path=None, resource=None):
    return route(func, GET, LIST, path, resource)
listing = get_list


def post_list(func, path=None, resource=None):
    return route(func, POST, LIST, path, resource)
create = post_list


def get_detail(func, path=None, resource=None):
    return route(func, GET, DETAIL, path, resource)
detail = get_detail


def put_detail(func, path=None, resource=None):
    return route(func, PUT, DETAIL, path, resource)
update = put_detail


def delete_detail(func, path=None, resource=None):
    return route(func, DELETE, DETAIL, path, resource)
delete = delete_detail


class ResourceApiBase(type):
    def __new__(cls, name, bases, attrs):
        super_new = super(ResourceApiBase, cls).__new__

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
                delattr(obj, '_route')

        attrs['_routes'] = routes
        return super_new(cls, name, bases, attrs)


@six.add_metaclass(ResourceApiBase)
class ResourceApi(object):
    # The resource this API is modelled on.
    resource = None

    # Handlers used to resolve a content-type from a request.
    # These are checked in the order defined until one returns a content-type
    content_type_resolvers = [
        content_type_resolvers.accepts_header(),
        content_type_resolvers.content_type_header(),
        content_type_resolvers.settings_default(),
    ]

    # Codecs that are supported for Encoding/Decoding resources.
    registered_codecs = CODECS
    url_prefix = r''

    def __init__(self, api_name=None):
        if api_name:
            self.api_name = api_name
        elif not hasattr(self, 'api_name'):
            self.api_name = "%ss" % self.resource._meta.name
