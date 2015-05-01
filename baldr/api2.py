from __future__ import absolute_import
import six
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from .api import ResourceApiCommon
from baldr.exceptions import ImmediateHttpResponse, ImmediateErrorHttpResponse
from baldr.resources import Error
from odin.exceptions import ValidationError

# Well known methods
HEAD = 'HEAD'
GET = 'GET'
POST = 'POST'
PUT = 'PUT'
DELETE = 'DELETE'

# Type of path
PATH_TYPE_LIST = 'list'
PATH_TYPE_DETAIL = 'detail'


def route(func=None, path_type=None, method=None, action=None, resource=None):
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
    :param path_type: Type of path, list/detail or custom.
    :param method: HTTP method(s) this function responses to.
    :param action: Action name
    :param resource: Specify the resource that this function
        encodes/decodes, default is the one specified on the ResourceAPI
        instance.

    """
    if isinstance(method, six.string_types):
        method = (method,)

    def inner(func):
        func.route = (path_type, method, action)
        func.resource = resource
        return func

    return inner(func) if func else inner


def list_action(func=None, name=None, method=GET, resource=None):
    return route(func, PATH_TYPE_LIST, method, name, resource)


def detail_action(func=None, name=None, method=GET, resource=None):
    return route(func, PATH_TYPE_DETAIL, method, name, resource)


listing = lambda f=None, resource=None: route(f, PATH_TYPE_LIST, GET, None, resource)
create = lambda f=None, resource=None: route(f, PATH_TYPE_LIST, POST, None, resource)
detail = lambda f=None, resource=None: route(f, PATH_TYPE_DETAIL, GET, None, resource)
update = lambda f=None, resource=None: route(f, PATH_TYPE_DETAIL, PUT, None, resource)
delete = lambda f=None, resource=None: route(f, PATH_TYPE_DETAIL, DELETE, None, resource)


class ResourceApiBase(type):
    def __new__(mcs, name, bases, attrs):
        super_new = super(ResourceApiBase, mcs).__new__

        # attrs will never be empty for classes declared in the standard way
        # (ie. with the `class` keyword). This is quite robust.
        if name == 'NewBase' and attrs == {}:
            return super_new(mcs, name, bases, attrs)

        parents = [b for b in bases if isinstance(b, ResourceApiBase) and not (b.__name__ == 'NewBase'
                                                                               and b.__mro__ == (b, object))]
        if not parents:
            # If this isn't a subclass of don't do anything special.
            return super_new(mcs, name, bases, attrs)

        # Build list of available routes.
        routes = []
        for view, obj in attrs.items():
            if callable(obj) and hasattr(obj, 'route'):
                path_type, method, action = obj.route
                routes.append((path_type, method, action, view))
                delattr(obj, 'route')
        attrs['routes'] = routes
        return super_new(mcs, name, bases, attrs)


@six.add_metaclass(ResourceApiBase)
class ResourceApi(ResourceApiCommon):
    """
    Base class for version 2 of the Resource API.

    The API now uses a meta class to extract routes from methods that have
    been decorated with route information.

    """
    # Table containing lookup information to simplify dispatch of incoming
    # requests to the appropriate views
    route_table = None

    def base_urls(self):
        url_table = {}
        route_table = {}
        for route in self.routes:
            path_type, methods, action, view = route
            route_key = "%s-%s" % (path_type, action) if action else path_type

            # Populate url_table
            if route_key not in url_table:
                if path_type == PATH_TYPE_LIST:
                    regex = action or r''
                else:
                    if action:
                        regex = r'(?P<resource_id>%s)/%s' % (self.resource_id_regex, action)
                    else:
                        regex = r'(?P<resource_id>%s)' % self.resource_id_regex

                url_table[route_key] = self.url(regex, self.wrap_dispatch(route_key))

            # Populate route table
            method_map = route_table.setdefault(route_key, {})
            for method in methods:
                method_map[method] = view

        # Store the route table at the same time
        self.route_table = route_table
        return list(url_table.values())

    def wrap_dispatch(self, route_key):
        """
        This method provides the main entry point for URL mappings in the ``base_urls`` method.
        """
        @csrf_exempt
        def wrapper(request, **kwargs):
            # Resolve content type used to encode/decode request/response content.
            content_type = self.resolve_content_type(request)
            try:
                request.codec = codec = self.registered_codecs[content_type]
            except KeyError:
                # This is just a plain HTTP response, we can't provide a rich response when the content type is unknown
                return HttpResponse(content="Content cannot be returned in the format requested.", status=406)

            try:
                result = self.dispatch(request, route_key, **kwargs)
            except Http404 as e:
                # Item is not found.
                status = 404
                resource = Error(status, 40400, str(e))
            except ImmediateHttpResponse as e:
                # An exception used to return a response immediately, skipping any further processing.
                response = HttpResponse(codec.dumps(e.resource), content_type=codec.CONTENT_TYPE, status=e.status)
                for key, value in (e.headers or {}).items():
                    response[key] = value
                return response
            except ValidationError as e:
                # Validation of a resource has failed.
                status = 400
                if hasattr(e, 'message_dict'):
                    resource = Error(status, 40000, "Fields failed validation.", meta=e.message_dict)
                else:
                    resource = Error(status, 40000, str(e))
            except PermissionDenied as e:
                status = 403
                resource = Error(status, 40300, "Permission denied", str(e))
            except NotImplementedError:
                # A mixin method has not been implemented, as defining a mixing is explicit this is considered a server
                # error that should be addressed.
                status = 501
                resource = Error(status, 50100, "This method has not been implemented.")
            except Exception as e:
                # Special case when a request raises a 500 error. If we are in debug mode and a default is used (ie
                # request does not explicitly specify a content type) fall back to the Django default exception page.
                if settings.DEBUG and getattr(content_type, 'is_default', False):
                    raise
                # Catch any other exceptions and pass them to the 500 handler for evaluation.
                resource = self.handle_500(request, e)
                status = resource.status
            else:
                if isinstance(result, tuple) and len(result) == 2:
                    resource, status = result
                else:
                    resource = result
                    status = 204 if result is None else 200  # Return 204 (No Content) if result is None.
            if resource is None:
                return HttpResponse(status=status)
            else:
                return HttpResponse(codec.dumps(resource), content_type=codec.CONTENT_TYPE, status=status)
        return wrapper

    def dispatch(self, request, route_key, **kwargs):
        """
        Primary method used to dispatch incoming requests to the appropriate method.
        """
        routes = self.route_table[route_key]
        try:
            request_method = routes[request.method]
        except KeyError:
            allow = ','.join(routes.keys())
            raise ImmediateErrorHttpResponse(405, 40500, "Method not allowed", headers={'Allow': allow},
                                             meta={'allow': allow})
        else:
            method = getattr(self, request_method, None)

        # Authorisation hook
        if hasattr(self, 'handle_authorisation'):
            self.handle_authorisation(request)

        # Allow for a pre_dispatch hook, a response from pre_dispatch would indicate an override of kwargs
        if hasattr(self, 'pre_dispatch'):
            response = self.pre_dispatch(request, **kwargs)
            if response is not None:
                kwargs = response

        result = method(request, **kwargs)

        # Allow for a post_dispatch hook, the response of which is returned
        if hasattr(self, 'post_dispatch'):
            return self.post_dispatch(request, result)
        else:
            return result
