from __future__ import absolute_import
from django.conf import settings
from django.conf.urls import url
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
import six
from . import content_type_resolvers
from .api import CODECS
from baldr.exceptions import ImmediateHttpResponse
from baldr.resources import Error
from odin.exceptions import ValidationError


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


def listing(func, path=None, resource=None):
    return route(func, GET, LIST, path, resource)


def create(func, path=None, resource=None):
    return route(func, POST, LIST, path, resource)


def detail(func, path=None, resource=None):
    return route(func, GET, DETAIL, path, resource)


def update(func, path=None, resource=None):
    return route(func, PUT, DETAIL, path, resource)


def delete(func, path=None, resource=None):
    return route(func, DELETE, DETAIL, path, resource)


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

        # Get list of routes
        routes = []
        for name, obj in attrs.items():
            if callable(obj) and hasattr(obj, '_route'):
                routes.append(obj._route)
                delattr(obj, '_route')

        attrs['_routes'] = routes
        return super_new(mcs, name, bases, attrs)


class ResourceApiCommon(object):
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

    def url(self, regex, view, kwargs=None, name=None, prefix=''):
        """
        Behaves like the django built in ``url`` method but constrains the URL to the API name.

        :param regex: This should be a part regex that applies only to the targeted method ie::

            self.url("(\d+)", ...)
        """
        if regex:
            return url(r'^%s/%s/?$' % (self.url_prefix + self.api_name.lower(), regex), view, kwargs, name, prefix)
        else:
            return url(r'^%s/?$' % (self.url_prefix + self.api_name.lower()), view, kwargs, name, prefix)

    @property
    def urls(self):
        """
        Return url conf for resource object.
        """
        return self.base_urls()

    def resolve_content_type(self, request):
        """
        Resolve the request content type from the request.

        :returns: Identified content type; or ``None`` if content type is not identified.

        """
        for resolver in self.content_type_resolvers:
            content_type = resolver(request)
            if content_type:
                return content_type

    def handle_500(self, request, exception):
        """
        Handle *un-handled* exceptions

        :param request: The request object.
        :param exception: The exception that was un-handled.
        :return: An ``HttpError`` response resource.

        """
        # This is an unknown exception, return an unknown error message.
        if settings.DEBUG:
            # If we are in debug mode return more details and the stack-trace.
            import sys
            import traceback

            the_trace = '\n'.join(traceback.format_exception(*(sys.exc_info())))
            return Error(500, 50000, "An unknown error has occurred, the developers have been notified.",
                         str(exception), the_trace)
        else:
            return Error(500, 50000, "An unknown error has occurred, the developers have been notified.")

    def wrap_view(self, view):
        """
        This method provides the main entry point for URL mappings in the ``base_urls`` method.
        """
        @csrf_exempt
        def wrapper(request, *args, **kwargs):
            # Resolve content type used to encode/decode request/response content.
            content_type = self.resolve_content_type(request)
            try:
                request.codec = codec = self.registered_codecs[content_type]
            except KeyError:
                # This is just a plain HTTP response, we can't provide a rich response when the content type is unknown
                return HttpResponse(content="Content cannot be returned in the format requested.", status=406)

            callback = getattr(self, view)
            try:
                result = callback(request, *args, **kwargs)
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

    def base_urls(self):
        """
        Base URL mappings for this API.
        """
        return []

    def handle_authorisation(self, request):
        """
        Evaluate if a request is authorised.

        :param request: The current Django request object.

        """
        pass

    def decode_body(self, request):
        """
        Helper method that ensures that decodes any body content into a string object (this is needed by the json
        module for example).
        """
        body = request.body
        if isinstance(body, bytes):
            return body.decode('UTF8')
        return body


@six.add_metaclass(ResourceApiBase)
class ResourceApi(ResourceApiCommon):
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

    def base_urls(self):
        return super(ResourceApi, self).base_urls() + [
            # List URL
            self.url(
                r'',
                self.wrap_view('dispatch_list')
            ),
            # Detail URL
            self.url(
                r'(?P<resource_id>%s)' % self.resource_id_regex,
                self.wrap_view('dispatch_detail')
            )
        ]

    def dispatch(self, request, request_type, **kwargs):
        """
        Primary method used to dispatch incoming requests to the appropriate method.
        """
        # allowed_methods = getattr(self, "%s_allowed_methods" % request_type, [])
        # request_method = self.method_check(request, allowed_methods)
        #
        # request.type = request_type
        #
        # method = getattr(self, "%s_%s" % (request_method, request_type), None)
        # if method is None:
        #     raise Http404()
        #
        # self.handle_authorisation(request)
        #
        # # Allow for a pre_dispatch hook, a response from pre_dispatch would indicate an override of kwargs
        # if hasattr(self, 'pre_dispatch'):
        #     response = self.pre_dispatch(request, **kwargs)
        #     if response is not None:
        #         kwargs = response
        #
        # result = method(request, **kwargs)
        #
        # # Allow for a post_dispatch hook, the response of which is returned
        # if hasattr(self, 'post_dispatch'):
        #     return self.post_dispatch(request, result)
        # else:
        #     return result