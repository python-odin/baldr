# -*- coding: utf-8 -*-
from __future__ import absolute_import

import logging
import six
import sys

from collections import OrderedDict
from django.conf import settings
from django.conf.urls import url, include
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt

from odin.codecs import json_codec
from odin.exceptions import CodecDecodeError, ValidationError
from odin.utils import getmeta, lazy_property

from .. import content_type_resolvers
from ..resources import Error
from ..exceptions import ImmediateErrorHttpResponse, ImmediateHttpResponse
from .constants import *  # noqa
from .route_decorators import *  # noqa


logger = logging.getLogger(__name__)

CODECS = {json_codec.CONTENT_TYPE: json_codec}
# Attempt to load other codecs that have dependencies
try:
    from odin.codecs import msgpack_codec
except ImportError:
    pass
else:
    CODECS[msgpack_codec.CONTENT_TYPE] = msgpack_codec


class ResourceApiCommon(object):
    # The resource this API is modelled on.
    resource = None
    resource_id_regex = r'\d+'

    # Handlers used to resolve the request content-type of the request body.
    # These are checked in the order defined until one returns a content-type.
    request_type_resolvers = [
        content_type_resolvers.content_type_header(),
        content_type_resolvers.accepts_header(),
        content_type_resolvers.settings_default(),
    ]

    # Handlers used to resolve the response content-type.
    # These are checked in the order defined until one returns a content-type.
    response_type_resolvers = [
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
            self.api_name = "%ss" % getmeta(self.resource).name

    def url(self, regex, view, kwargs=None, name=None, prefix=''):
        """
        Behaves like the django built in ``url`` method but constrains the URL to the API name.

        Regex should be a part regex that applies only to the targeted method ie::

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

    def resolve_request_type(self, request):
        """
        Resolve the request content type from the request.

        :returns: Identified content type; or ``None`` if content type is not identified.

        """
        for resolver in self.request_type_resolvers:
            content_type = resolver(request)
            if content_type:
                return content_type

    def resolve_response_type(self, request):
        """
        Resolve the response content type from the request.

        :returns: Identified content type; or ``None`` if content type is not identified.

        """
        for resolver in self.response_type_resolvers:
            content_type = resolver(request)
            if content_type:
                return content_type

    @staticmethod
    def handle_500(request, exception):
        """
        Handle *un-handled* exceptions

        :param request: The request object.
        :param exception: The exception that was un-handled.
        :return: An ``HttpError`` response resource.

        """
        exc_info = sys.exc_info()

        # This is an unknown exception, return an unknown error message.
        if settings.DEBUG:
            # If we are in debug mode return more details and the stack-trace.
            import traceback
            the_trace = '\n'.join(traceback.format_exception(*exc_info))
            return Error(500, 50000, "An unknown error has occurred, the developers have been notified.",
                         str(exception), the_trace)
        else:
            logger.error('Internal Server Error: %s', request.path, exc_info=exc_info, extra={
                'status_code': 500,
                'request': request
            })
            return Error(500, 50000, "An unknown error has occurred, the developers have been notified.")

    def base_urls(self):
        """
        Base URL mappings for this API.
        """
        return []

    @staticmethod
    def decode_body(request):
        """
        Helper method that ensures that decodes any body content into a string object (this is needed by the json
        module for example).
        """
        body = request.body
        if isinstance(body, bytes):
            return body.decode('UTF8')
        return body

    def resource_from_body(self, request, allow_multiple=False, resource=None):
        """
        Get a resource instance from ``request.body``.
        """
        resource = resource or self.resource

        try:
            body = self.decode_body(request)
        except UnicodeDecodeError as ude:
            raise ImmediateErrorHttpResponse(400, 40099, "Unable to decode request body.", str(ude))

        try:
            resource = request.request_codec.loads(body, resource=resource, full_clean=False)
        except ValueError as ve:
            raise ImmediateErrorHttpResponse(400, 40098, "Unable to load resource.", str(ve))
        except CodecDecodeError as cde:
            raise ImmediateErrorHttpResponse(400, 40096, "Unable to decode body.", str(cde))

        # Check an array of data hasn't been supplied
        if not allow_multiple and isinstance(resource, list):
            raise ImmediateErrorHttpResponse(400, 40097, "Expected a single resource not a list.")

        return resource

    def dispatch_to_view(self, view, request, *args, **kwargs):
        raise NotImplementedError()

    def wrap_view(self, view):
        """
        This method provides the main entry point for URL mappings in the ``base_urls`` method.
        """
        @csrf_exempt
        def wrapper(request, *args, **kwargs):
            # Resolve content type used to encode/decode request/response content.
            response_type = self.resolve_response_type(request)
            request_type = self.resolve_request_type(request)
            try:
                request.request_codec = self.registered_codecs[request_type]
                request.response_codec = response_codec = self.registered_codecs[response_type]
            except KeyError:
                # This is just a plain HTTP response, we can't provide a rich response when the content type is unknown
                return HttpResponse(content="Content cannot be returned in the format requested.", status=406)

            try:
                result = self.dispatch_to_view(view, request, *args, **kwargs)
            except Http404 as e:
                # Item is not found.
                status = 404
                resource = Error(status, 40400, str(e))

            except ImmediateHttpResponse as e:
                # An exception used to return a response immediately, skipping any further processing.
                response = HttpResponse(
                    response_codec.dumps(e.resource),
                    content_type=response_codec.CONTENT_TYPE,
                    status=e.status
                )
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
                if settings.DEBUG and getattr(response_type, 'is_default', False):
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
            elif isinstance(resource, HttpResponse):
                return resource
            else:
                return HttpResponse(
                    response_codec.dumps(resource),
                    content_type=response_codec.CONTENT_TYPE,
                    status=status
                )
        return wrapper


class ResourceApiBase(type):
    def __new__(mcs, name, bases, attrs):
        super_new = super(ResourceApiBase, mcs).__new__

        # attrs will never be empty for classes declared in the standard way
        # (ie. with the `class` keyword). This is quite robust.
        if name == 'NewBase' and attrs == {}:
            return super_new(mcs, name, bases, attrs)

        parents = [
            b for b in bases
            if isinstance(b, ResourceApiBase) and not (b.__name__ == 'NewBase' and b.__mro__ == (b, object))
        ]
        if not parents:
            # If this isn't a subclass of don't do anything special.
            return super_new(mcs, name, bases, attrs)

        routes = []

        # Get local routes and sort them by route number
        for view, obj in attrs.items():
            if callable(obj) and hasattr(obj, 'route'):
                route_number, path_type, method, action_name = obj.route
                routes.append((route_number, path_type, method, action_name, view))
                delattr(obj, 'route')
        routes = sorted(routes, key=lambda o: o[0])

        # Get routes from parent objects
        for parent in parents:
            if hasattr(parent, 'routes'):
                routes.extend(parent.routes)

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

    # Respond to the options method.
    respond_to_options = True

    def base_urls(self):
        url_table = OrderedDict()
        route_table = {}
        for route_ in self.routes:
            route_number, path_type, methods, action_name, view = route_
            route_key = "%s-%s" % (path_type, action_name) if action_name else path_type

            # Populate url_table
            if route_key not in url_table:
                if path_type == PATH_TYPE_COLLECTION:
                    regex = action_name or r''
                else:
                    if action_name:
                        regex = r'(?P<resource_id>%s)/%s' % (self.resource_id_regex, action_name)
                    else:
                        regex = r'(?P<resource_id>%s)' % self.resource_id_regex

                url_table[route_key] = self.url(regex, self.wrap_view(route_key))

            # Populate route table
            method_map = route_table.setdefault(route_key, {})
            for method in methods:
                method_map[method] = view

            # Add options
            if self.respond_to_options:
                method_map.setdefault(constants.OPTIONS, 'options_response')

        # Store the route table at the same time
        self.route_table = dict(route_table)
        return list(url_table.values())

    def dispatch_to_view(self, route_key, request, *args, **kwargs):
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

        # Apply route key to kwargs on OPTIONS requests
        if request.method == constants.OPTIONS:
            kwargs['route_key'] = route_key

        result = method(request, **kwargs)

        # Allow for a post_dispatch hook, the response of which is returned
        if hasattr(self, 'post_dispatch'):
            return self.post_dispatch(request, result)
        else:
            return result

    def options_response(self, request, route_key, **kwargs):
        routes = self.route_table[route_key]
        response = HttpResponse(status=204)
        response['Allow'] = ','.join(method for method, route in routes.items() if route != 'options_response')
        return response


class ApiCollection(object):
    """
    Collection of several resource API's.
    Along with helper methods for building URL patterns.
    ::
        urlpatterns += Api(
            ApiCollection(
                UserApi(),
                MyApi(),
            )
        ).patterns()
    """
    def __init__(self, *resource_apis, **kwargs):
        self.api_name = kwargs.pop('api_name', 'api')
        self.resource_apis = resource_apis

    @lazy_property
    def urls(self):
        urls = []
        for resource_api in self.resource_apis:
            urls.extend(resource_api.urls)
        return urls

    def include(self, namespace=None):
        return include(self.urls, namespace)

    def patterns(self, api_name=None):
        api_name = api_name or self.api_name
        return [url(r'^%s/' % api_name, self.include())]


class ApiVersion(ApiCollection):
    """
    A versioned collection of several resource API's.
    Along with helper methods for building URL patterns.
    """
    def __init__(self, *resource_apis, **kwargs):
        kwargs.setdefault('api_name', kwargs.pop('version', 'v1'))
        super(ApiVersion, self).__init__(*resource_apis, **kwargs)


class Api(object):
    """
    An API (made up of versions).
    ::
        urlpatterns += Api(
            ApiVersion(
                UserApi(),
                MyApi(),
                version='v1',
            )
        ).patterns()
    """
    def __init__(self, *versions, **kwargs):
        self.versions = versions
        self.api_name = kwargs.get('api_name', 'api')

    def patterns(self):
        urls = [url(r'^%s/%s/' % (self.api_name, v.api_name), v.include()) for v in self.versions]
        urls.append(url(r'^%s/$' % self.api_name, self._unknown_version))
        return urls

    def _unknown_version(self, _):
        supported_versions = [v.api_name for v in self.versions]
        return HttpResponse(
            "Unsupported API version. Available versions: %s" % ', '.join(supported_versions),
            status=418  # I'm a teapot... Is technically a bad request but makes sense to have a different status code.
        )
