from __future__ import absolute_import
from collections import OrderedDict
import six
from django.http import HttpResponse

from .constants import *  # noqa
from .route_decorators import *  # noqa
from ..api import ResourceApiCommon
from ..exceptions import ImmediateErrorHttpResponse


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
