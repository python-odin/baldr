# coding=utf-8
from django.conf import settings
from django.conf.urls import url, patterns
from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from baldr.exceptions import HttpError, ImmediateHttpResponse, ImmediateErrorHttpResponse
import odin
from odin.codecs import json_codec
from odin.exceptions import ValidationError

CONTENT_TYPE_MAP = {
    'text/json': 'json',
    'application/json': 'json',
    'text/xml': 'xml',
}
CONTENT_ENCODINGS = {
    'json': json_codec,
}


class ResourceApi(object):
    """RESTful API using Odin resources."""
    resource = None
    list_allowed_methods = ['get']
    detail_allowed_methods = ['get', 'post']
    supported_encodings = ['json']

    def __init__(self, api_name=None):
        assert issubclass(self.resource, odin.Resource)

        if not api_name:
            api_name = self.resource._meta.name
        self.name = api_name

    def _handle_500(self, e):
        # This is an unknown exception, return an unknown error message.
        if settings.DEBUG:
            # If we are in debug mode return more details and the stack-trace.
            import traceback
            import sys
            the_trace = '\n'.join(traceback.format_exception(*(sys.exc_info())))
            return HttpError(status=500, code=50000,
                                     message="An unknown error has occurred, the developers have been notified.",
                                     developer_message=str(e),
                                     meta=the_trace)
        else:
            return HttpError(status=500, code=50000,
                                     message="An unknown error has occurred, the developers have been notified.")

    def wrap_view(self, view):
        @csrf_exempt
        def wrapper(request, *args, **kwargs):
            encoder = self.determine_request_type(request)
            try:
                callback = getattr(self, view)
                resource, status = callback(request, *args, **kwargs)
            except ImmediateHttpResponse as e:
                resource = e.resource
            except NotImplementedError:
                resource = HttpError(501, code=50100, message="This method has not been implemented.")
            except Http404 as e:
                resource = HttpError(404, code=40400, message=e.message)
            except ValidationError as e:
                if hasattr(e, 'message_dict'):
                    resource = HttpError(400, code=40001, message="Fields failed validation.")
                else:
                    resource = HttpError(400, code=40001, message=e.message)
            except Exception as e:
                resource = self._handle_500(e)
                status = 500
            return HttpResponse(encoder.dumps(resource), content_type='text/json', status=status)
        return wrapper

    def base_urls(self):
        return [
            url(r'^%s/$' % self.name.lower(), self.wrap_view('dispatch_list')),
            url(r'^%s/(?P<id>[-\w]+)/$' % self.name.lower(), self.wrap_view('dispatch_detail')),
        ]

    @property
    def urls(self):
        """
        Return url conf for resource object.
        """
        return patterns('', *self.base_urls())

    def dispatch_list(self, request, **kwargs):
        return self.dispatch(request, 'list', **kwargs)

    def dispatch_detail(self, request, **kwargs):
        return self.dispatch(request, 'detail', **kwargs)

    def dispatch(self, request, request_type, **kwargs):

        allowed_methods = getattr(self, "%s_allowed_methods" % request_type, None)

        request_method = self.method_check(request, allowed=allowed_methods)
        method = getattr(self, "%s_%s" % (request_method, request_type))

        if method is None:
            raise NotImplementedError()

        response = method(request, **kwargs)
        # if not isinstance(response, HttpResponse):
        #     return http.HttpResponseNoContent()
        return response

    def determine_request_type(self, request):
        encoding_name = CONTENT_TYPE_MAP.get(request.META.get('content-type'), 'json')
        encoding_name = request.GET.get('type', encoding_name)
        if encoding_name not in self.supported_encodings:
            raise ImediateHttpResponse(response)

        return CONTENT_ENCODINGS.get(encoding_name)

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
            raise Http404('No `%s` found that matches request.' % self.name.title())

        if not request_method in allowed:
            raise ImmediateErrorHttpResponse(405, 40500, "Method not allowed", headers={
                'Allow': allows
            })

        return request_method
