# coding=utf-8
from django.conf import settings
from django.conf.urls import url, patterns
from django.http import HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
import odin
from odin.codecs import json_codec
from odin.exceptions import ValidationError
from baldr import content_type_resolvers
from baldr.exceptions import ImmediateErrorHttpResponse, ImmediateHttpResponse
from baldr.resources import Error


CODECS = {json_codec.CONTENT_TYPE: json_codec}
# Attempt to load other codecs that have dependencies
try:
    from odin.codecs import msgpack_codec
    CODECS[msgpack_codec.CONTENT_TYPE] = msgpack_codec
except ImportError:
    pass


class ResourceApiBase(object):
    """
    Provides an API that returns a specified resource object.
    """
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

    def __init__(self, api_name=None):
        assert issubclass(self.resource, odin.Resource)

        self.api_name = api_name if api_name else self.resource._meta.name

    @property
    def urls(self):
        """
        Return url conf for resource object.
        """
        return patterns('', *self.base_urls())

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
                status = 404
                resource = Error(status, 40400, str(e))
            except ImmediateHttpResponse as e:
                response = HttpResponse(codec.dumps(e.resource), content_type=codec.CONTENT_TYPE, status=e.status)
                for key, value in (e.headers or {}).items():
                    response[key] = value
                return response
            except ValidationError as e:
                status = 400
                if hasattr(e, 'message_dict'):
                    resource = Error(status, 40000, "Fields failed validation.", meta=e.message_dict)
                else:
                    resource = Error(status, 40000, str(e))
            except Exception as e:
                resource = self.handle_500(request, e)
                status = resource.status
            else:
                if isinstance(result, tuple) and len(result) == 2:
                    resource, status = result
                else:
                    resource = result
                    status = 200
            return HttpResponse(codec.dumps(resource), content_type=codec.CONTENT_TYPE, status=status)
        return wrapper

    def base_urls(self):
        """
        Base URL mappings for this API.
        """
        return []

    def dispatch(self, request, request_type, **kwargs):
        """
        Primary method used to dispatch incoming requests to the appropriate method.
        """
        allowed_methods = getattr(self, "%s_allowed_methods" % request_type, [])
        request_method = self.method_check(request, allowed_methods)

        self.check_authorised(request, request_type, request_method)

        method = getattr(self, "%s_%s" % (request_method, request_type), None)
        if method is None:
            raise NotImplementedError()

        return method(request, **kwargs)

    def method_check(self, request, allowed):
        request_method = request.method.lower()

        if not allowed:
            raise Http404('`%s` not found.' % self.api_name.title())

        if not request_method in allowed:
            raise ImmediateErrorHttpResponse(405, 40500, "Method not allowed", headers={
                'Allow': ','.join(map(str.upper, allowed))
            })
        return request_method

    def check_authorised(self, request, request_type, request_method):
        """
        Evaluate if a request is authorised.

        :param request: The current Django request object.
        :param request_type: The current request type.
        :param request_method: The current request method.

        """
        pass


class ResourceApi(ResourceApiBase):
    list_allowed_methods = ['get']
    detail_allowed_methods = ['get']

    def base_urls(self):
        return super(ResourceApi, self).base_urls() + [
            url(r'^%s/$' % self.api_name.lower(), self.wrap_view('dispatch_list')),
            url(r'^%s/(?P<id>\d+)/$' % self.api_name.lower(), self.wrap_view('dispatch_detail')),
        ]

    def dispatch_list(self, request, **kwargs):
        return self.dispatch(request, 'list', **kwargs)

    def dispatch_detail(self, request, **kwargs):
        return self.dispatch(request, 'detail', **kwargs)
