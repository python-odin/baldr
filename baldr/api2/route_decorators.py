from __future__ import absolute_import
import six
from baldr.resources import Listing
from .constants import *

__all__ = (
    # Basic routes
    'route', 'detail_route', 'action', 'detail_action',
    # Handlers
    'list_response',
    # Shortcuts
    'listing', 'create', 'detail', 'update', 'delete'
)

route_count = 0


# Route definition decorators

def route(func=None, name=None, path_type=PATH_TYPE_BASE, method=GET, resource=None):
    """
    Decorator for defining a route. Usually one of the helpers (listing,
    create, detail, update, delete) would be used in place of the route
    decorator.

    Usage::

        class ItemApi(ResourceApi):
            resource = Item

            @route(path_type=PATH_TYPE_LIST, method=GET)
            def list_items(self, request):

                ...

                return items


    :param func: Function we are routing
    :param name: Action name
    :param path_type: Type of path, list/detail or custom.
    :param method: HTTP method(s) this function responses to.
    :param resource: Specify the resource that this function
        encodes/decodes, default is the one specified on the ResourceAPI
        instance.

    """
    if isinstance(method, six.string_types):
        method = (method,)

    global route_count
    route_number = route_count
    route_count += 1

    def inner(func):
        func.route = (route_number, path_type, method, name)
        func.resource = resource
        return func

    return inner(func) if func else inner

action = route


def detail_route(func=None, name=None, method=GET, resource=None):
    return route(func, name, PATH_TYPE_DETAIL, method, resource)

detail_action = detail_route


# Handlers

def list_response(func=None):
    """
    Handle processing a list. It is assumed decorator will operate on a class.
    """
    def inner(func):
        def wrapper(self, request, *args, **kwargs):
            # Get paging args from query string
            offset = kwargs['offset'] = int(request.GET.get('offset', 0))
            limit = kwargs['limit'] = int(request.GET.get('limit', 50))
            result = func(self, request, *args, **kwargs)
            if result:
                if isinstance(result, tuple) and len(result) == 2:
                    result, total_count = result
                else:
                    total_count = None
                return Listing(list(result), limit, offset, total_count)
        return wrapper
    return inner(func) if func else inner


# Shortcut methods

listing = lambda f=None, name=None, resource=None: route(list_response(f), name, PATH_TYPE_BASE, GET, resource)
create = lambda f=None, name=None, resource=None: route(f, name, PATH_TYPE_BASE, POST, resource)
detail = lambda f=None, name=None, resource=None: route(f, name, PATH_TYPE_DETAIL, GET, resource)
update = lambda f=None, name=None, resource=None: route(f, name, PATH_TYPE_DETAIL, PUT, resource)
delete = lambda f=None, name=None, resource=None: route(f, name, PATH_TYPE_DETAIL, DELETE, resource)
