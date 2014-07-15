# coding=utf-8
from django import http
from django.conf import settings
from django.conf.urls import url, patterns
from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import odin
from odin.codecs import json_codec, xml_codec
from odin.exceptions import ValidationError
from baldr.exceptions import ImmediateErrorHttpResponse, ImmediateHttpResponse
from baldr.resources import HttpError

CONTENT_TYPE_MAP = {
    json_codec.CONTENT_TYPE: 'json',
    xml_codec.CONTENT_TYPE: 'xml',
}

CONTENT_ENCODINGS = {
    'json': json_codec,
}


class ResourceApi(object):
    """RESTful API user Odin resources"""
    resource = None
    list_allowed_methods = ['get']
    detail_allowed_methods = ['get', 'post']
    supported_encodings = ['json']

    def __init__(self, api_name=None):
        assert issubclass(self.resource, odin.Resource)

        self.api_name = api_name if api_name else self.resource._meta.name

    def determine_request_encoding(self, request):
        # Get the encoding name from the content-type header
        encoding_name = CONTENT_TYPE_MAP.get(request.META.get('content-type'), 'json')
        # If the content-type is specified in the get parameters use that.
        encoding_name = request.GET.get('content-type', encoding_name)

        return CONTENT_ENCODINGS[encoding_name]

    def handle_500(self, exception):
        # This is an unknown exception, return an unknown error message.
        if settings.DEBUG:
            # If we are in debug mode return more details and the stack-trace.
            import sys
            import traceback
            the_trace = '\n'.join(traceback.format_exception(*(sys.exc_info())))
            return HttpError(status=500,
                             message="An unknown error has occurred, the developers have been notified.",
                             developer_message=str(exception),
                             meta=the_trace)
        else:
            return HttpError(status=500, message="An unknown error has occurred, the developers have been notified.")

    def wrap_view(self, view):
        @csrf_exempt
        def wrapper(request, *args, **kwargs):
            # Get encoding
            try:
                encoder = self.determine_request_encoding(request)
            except KeyError:
                return http.HttpResponseBadRequest("Invalid content type.")

            # Make callback and handle errors
            try:
                callback = getattr(self, view)
                result = callback(request, *args, **kwargs)
            except ImmediateErrorHttpResponse as e:
                resource = e.resource
                status = resource.status
            except NotImplementedError:
                status = 501
                resource = HttpError(status=status, code=50100, message="This method has not been implemented.")
            except Http404 as e:
                status = 404
                resource = HttpError(status=status, code=40400, message=e.message)
            except ValidationError as e:
                status = 400
                if hasattr(e, 'message_dict'):
                    resource = HttpError(status=status, code=40000, message="Fields failed validation.")
                else:
                    resource = HttpError(status=status, code=40000, message=e.message)
            except Exception as e:
                resource = self.handle_500(e)
                status = 500
            else:
                if isinstance(result, tuple) and len(result) == 2:
                    resource, status = result
                else:
                    resource = result
                    status = 200
            return HttpResponse(encoder.dumps(resource), content_type='text/json', status=status)
        return wrapper

    def base_urls(self):
        return [
            url(r'^%s/$' % self.api_name.lower(), self.wrap_view('dispatch_list')),
            url(r'^%s/(?P<id>[-\w]+)/$' % self.api_name.lower(), self.wrap_view('dispatch_detail')),
        ]

    @property
    def urls(self):
        """
        Return url conf for resource object.
        """
        return patterns('', *self.base_urls())

    def dispatch_list(self, request, **kwargs):
        """
        Dispatch listing methods.
        """
        return self.dispatch(request, 'list', **kwargs)

    def dispatch_detail(self, request, **kwargs):
        """
        Dispatch get (singular) methods.
        """
        return self.dispatch(request, 'detail', **kwargs)

    def dispatch(self, request, request_type, **kwargs):
        allowed_methods = getattr(self, "%s_allowed_methods" % request_type, None)
        request_method = self.method_check(request, allowed=allowed_methods)

        method = getattr(self, "%s_%s" % (request_method, request_type), None)
        if method is None:
            raise NotImplementedError()

        return method(request, **kwargs)

    def method_check(self, request, allowed=None):
        if allowed is None:
            allowed = []

        request_method = request.method.lower()
        allows = ','.join(map(str.upper, allowed))

        if request_method == "options":
            response = HttpError()
            response['Allow'] = allows
            raise ImmediateHttpResponse(response)

        if not allowed:
            raise Http404('No `%s` found that matches request.' % self.api_name.title())

        if not request_method in allowed:
            raise ImmediateErrorHttpResponse(405, 40500, "Method not allowed", headers={
                'Allow': allows
            })

        return request_method
