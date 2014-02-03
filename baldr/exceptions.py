# -*- coding: utf-8 -*-
from baldr.resources import HttpError


class ImmediateHttpResponse(Exception):
    """
    A response that should be returned Immediately!
    """
    def __init__(self, resource):
        self.resource = resource


class ImmediateErrorHttpResponse(ImmediateHttpResponse):
    """
    An error response that should be returned Immediately!
    """
    def __init__(self, headers=None, **kwargs):
        resource = HttpError(**kwargs)
        if headers:
            for name, value in headers.items():
                resource[name] = value

        super(ImmediateErrorHttpResponse, self).__init__(resource)
