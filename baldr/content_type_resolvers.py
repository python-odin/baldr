# coding=utf-8
from django.conf import settings


def accepts_header():
    """
    Resolve content type from the accepts header of a request.
    """
    def inner(request):
        return request.META.get('accepts')
    return inner


def content_type_header():
    """
    Resolve content type from the content_type header of a request.
    """
    def inner(request):
        return request.META.get('content-type')
    return inner


class DefaultString(str):
    is_default = True


def specific_default(content_type):
    """
    Specify a specific default content type.

    :param content_type: The content type to use.
    """
    def inner(_):
        return DefaultString(content_type)
    return inner


def settings_default(content_type='application/json'):
    """
    Default from ``settings.BALDR_DEFAULT_CONTENT_TYPE``.

    :param content_type: The content type to use as a fallback if setting is not defined.
    """
    def inner(_):
        return DefaultString(getattr(settings, 'BALDR_DEFAULT_CONTENT_TYPE', content_type))
    return inner
