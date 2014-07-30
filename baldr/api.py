# coding=utf-8
from django.conf import settings
from django.conf.urls import url, patterns, include
from django.http import HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from odin.codecs import json_codec
from odin.exceptions import ValidationError
from baldr import content_type_resolvers
from baldr.exceptions import ImmediateErrorHttpResponse, ImmediateHttpResponse
from baldr.resources import Error, Listing


CODECS = {json_codec.CONTENT_TYPE: json_codec}
# Attempt to load other codecs that have dependencies
try:
    from odin.codecs import msgpack_codec
    CODECS[msgpack_codec.CONTENT_TYPE] = msgpack_codec
except ImportError:
    pass


class ResourceApiBase(object):
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
        if api_name:
            self.api_name = api_name
        elif not hasattr(self, 'api_name'):
            self.api_name = "%ss" % self.resource._meta.name

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
            except NotImplementedError:
                # A mixin method has not been implemented, as defining a mixing is explicit this is considered a server
                # error that should be addressed.
                status = 501
                resource = Error(status, 50100, "This method has not been implemented.")
            except Exception as e:
                # Catch any other exceptions and pass them to the 500 handler for evaluation.
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

        self.handle_authorisation(request, request_type, request_method)

        method = getattr(self, "%s_%s" % (request_method, request_type), None)
        if method is None:
            raise NotImplementedError()

        return method(request, **kwargs)

    def method_check(self, request, allowed):
        request_method = request.method.lower()

        if not allowed:
            raise Http404('`%s` not found.' % self.api_name)

        if request_method not in allowed:
            raise ImmediateErrorHttpResponse(405, 40500, "Method not allowed", headers={
                'Allow': ','.join(map(str.upper, allowed))
            })
        return request_method

    def handle_authorisation(self, request, request_type, request_method):
        """
        Evaluate if a request is authorised.

        :param request: The current Django request object.
        :param request_type: The current request type.
        :param request_method: The current request method.

        """
        pass


class ResourceApi(ResourceApiBase):
    """
    Provides an API that returns a specified resource object.
    """
    list_allowed_methods = ['get']
    detail_allowed_methods = ['get']

    def base_urls(self):
        return super(ResourceApi, self).base_urls() + [
            url(r'^%s/$' % self.api_name.lower(), self.wrap_view('dispatch_list')),
            url(r'^%s/(?P<resource_id>\d+)/$' % self.api_name.lower(), self.wrap_view('dispatch_detail')),
        ]

    def dispatch_list(self, request, **kwargs):
        return self.dispatch(request, 'list', **kwargs)

    def dispatch_detail(self, request, **kwargs):
        return self.dispatch(request, 'detail', **kwargs)


class ListMixin(ResourceApi):
    """
    Mixin to the resource API that provides a nice listing API.
    """
    def get_list(self, request):
        offset = int(request.GET.get('offset', 0))
        limit = int(request.GET.get('limit', 50))
        return Listing(
            self.list_resources(request, offset, limit),
            limit, offset
        )

    def list_resources(self, request, offset, limit):
        """
        Load resources
        :param limit: Resource count limit.
        :param offset: Offset within the list to return.
        :return: List of resource objects.
        """
        raise NotImplementedError


class CreateMixin(ResourceApi):
    """
    Mixin to the resource API to provide a Create API.
    """
    def __init__(self, *args, **kwargs):
        super(CreateMixin, self).__init__(*args, **kwargs)
        self.list_allowed_methods.append('post')

    def post_detail(self, request):
        resource = request.codec.loads(request.data, resource=self.resource)
        return self.create_resource(request, resource)

    def create_resource(self, request, resource):
        """
        Create method.
        """
        raise NotImplementedError


class RetrieveMixin(ResourceApi):
    """
    Mixin to the resource API to provide a Retrieve API.
    """
    def get_detail(self, request, resource_id):
        return self.retrieve_resource(request, resource_id)

    def retrieve_resource(self, request, resource_id):
        raise NotImplementedError


class UpdateMixin(ResourceApi):
    """
    Mixin to the resource API to provide a Update API.
    """
    def __init__(self, *args, **kwargs):
        super(UpdateMixin, self).__init__(*args, **kwargs)
        self.detail_allowed_methods.append('post')

    def post_detail(self, request, resource_id):
        resource = request.codec.loads(request.data, resource=self.resource)
        return self.update_resource(request, resource_id, resource)

    def update_resource(self, request, resource_id, resource):
        raise NotImplementedError


class DeleteMixin(ResourceApi):
    """
    Mixin to the resource API to provide a Delete API.
    """
    def __init__(self, *args, **kwargs):
        super(DeleteMixin, self).__init__(*args, **kwargs)
        self.detail_allowed_methods.append('delete')

    def post_detail(self, request, resource_id):
        return self.delete_resource(request, resource_id)

    def delete_resource(self, request, resource_id):
        raise NotImplementedError


class ApiCollection(object):
    """
    Collection of several resource API's.

    Along with helper methods for building URL patterns.
    """
    def __init__(self, *resource_apis, **kwargs):
        self.api_name = kwargs.pop('api_name', 'api')
        self.resource_apis = resource_apis

    @property
    def urls(self):
        if not hasattr(self, '_urls'):
            urls = []
            for resource_api in self.resource_apis:
                urls.extend(resource_api.urls)
            self._urls = urls
        return self._urls

    def include(self, namespace=None):
        return include(self.urls, namespace)

    def patterns(self):
        return [url(r'^%s/' % self.api_name, self.include())]
