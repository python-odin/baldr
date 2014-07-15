# coding=utf-8
from django.conf import settings
from django.conf.urls import url, patterns
from django.http import HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
import odin
from odin.codecs import json_codec
from odin.exceptions import ValidationError
from baldr import content_type_resolvers
from baldr.exceptions import ImmediateErrorHttpResponse
from baldr.resources import HttpError


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

    # Handlers used to resolve a content type from a request.
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
            return HttpError(
                status=500,
                message="An unknown error has occurred, the developers have been notified.",
                developer_message=str(exception),
                meta=the_trace
            )
        else:
            return HttpError(status=500, message="An unknown error has occurred, the developers have been notified.")

    def wrap_view(self, view):
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
            except NotImplementedError:
                status = 405
                resource = HttpError(status=status, code=40501, message="This method has not been implemented.")
            except Http404 as e:
                status = 404
                resource = HttpError(status=status, code=40400, message=str(e))
            except ImmediateErrorHttpResponse as e:
                resource = e.resource
                status = resource.status
            except ValidationError as e:
                status = 400
                if hasattr(e, 'message_dict'):
                    resource = HttpError(status=status, code=40000, message="Fields failed validation.")
                else:
                    resource = HttpError(status=status, code=40000, message=str(e))
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

    def dispatch(self, request, request_type, *args, **kwargs):
        request_method = self.method_check(request)

        method = getattr(self, "%s_%s" % (request_method, request_type), None)
        if method is None:
            raise NotImplementedError()

        return method(request, **kwargs)

    # def method_check(self, request):
    #     request_method = request.method.lower()
    #     allows = ','.join(map(str.upper, allowed))
    #
    #     if request_method == "options":
    #         response = HttpError()
    #         response['Allow'] = allows
    #         raise ImmediateHttpResponse(response)
    #
    #     if not allowed:
    #         raise Http404('No `%s` found that matches request.' % self.api_name.title())
    #
    #     if not request_method in allowed:
    #         raise ImmediateErrorHttpResponse(405, 40500, "Method not allowed", headers={
    #             'Allow': allows
    #         })
    #
    #     return request_method


class ResourceApi(ResourceApiBase):
    def base_urls(self):
        return super(ResourceApi, self).base_urls() + [
            url(r'^%s/$' % self.api_name.lower(), self.wrap_view('dispatch_list')),
            url(r'^%s/(?P<id>[-\w]+)/$' % self.api_name.lower(), self.wrap_view('dispatch_detail')),
        ]

    def dispatch_list(self, request, *args, **kwargs):
        return self.dispatch(request, 'list', *args, **kwargs)

    def dispatch_detail(self, request, *args, **kwargs):
        return self.dispatch(request, 'detail', *args, **kwargs)
