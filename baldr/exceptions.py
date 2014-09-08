# -*- coding: utf-8 -*-
from baldr.resources import Error


class ImmediateHttpResponse(Exception):
    """
    A response that should be returned Immediately!
    """
    def __init__(self, resource, status=200, headers=None):
        self.resource = resource
        self.status = status
        self.headers = headers


class ImmediateErrorHttpResponse(ImmediateHttpResponse):
    """
    An error response that should be returned Immediately!
    """
    def __init__(self, status, sub_status, message, developer_message=None, meta=None, headers=None):
        super(ImmediateErrorHttpResponse, self).__init__(
            Error(status, sub_status, message, developer_message, meta),
            status, headers
        )
