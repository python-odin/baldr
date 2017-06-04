# -*- coding: utf-8 -*-
import odin
import six

from django.core import exceptions as django_exceptions
from django.forms import widgets
from django.forms.fields import CharField
from django.utils.translation import ugettext_lazy as _
from odin import exceptions as odin_exceptions
from odin.codecs import json_codec
from odin.utils import getmeta


class ResourceField(CharField):
    """
    Form field that wraps an Odin resource.
    """

    widget = widgets.Textarea

    default_error_messages = {
        'invalid': _('This field is not a valid %s resource.'),
    }

    def __init__(self, resource_type, codec=json_codec, codec_kargs=None, *args, **kwargs):
        assert issubclass(resource_type, odin.Resource)
        super(ResourceField, self).__init__(*args, **kwargs)

        self.resource_type = resource_type
        self.codec = codec
        self.codec_kwargs = dict(indent=2, sort_keys=True) if codec_kargs is None else codec_kargs

    def prepare_value(self, value):
        if value is None:
            return ''
        elif isinstance(value, (list, tuple, odin.Resource)):
            return self.codec.dumps(value, **self.codec_kwargs)
        else:
            return str(value)

    def to_python(self, value):
        if value is None or value == '':
            return

        if isinstance(value, self.resource_type):
            return value

        if isinstance(value, six.string_types):
            try:
                return self.codec.loads(value, self.resource_type, full_clean=False)
            except odin_exceptions.ValidationError as ve:
                if hasattr(ve, 'message_dict'):
                    raise django_exceptions.ValidationError(str(ve.message_dict))
                else:
                    raise django_exceptions.ValidationError(ve.messages)
            except odin_exceptions.CodecDecodeError as cde:
                raise django_exceptions.ValidationError(str(cde))
            except ValueError as ve:
                raise django_exceptions.ValidationError(str(ve))

        raise django_exceptions.ValidationError(
            self.error_messages['invalid'] % getmeta(self.resource_type).resource_name, code='invalid'
        )

    def validate(self, value):
        super(ResourceField, self).validate(value)

        if value is None:
            return

        if isinstance(value, self.resource_type):
            try:
                value.full_clean()
            except odin_exceptions.ValidationError as ve:
                if hasattr(ve, 'message_dict'):
                    raise django_exceptions.ValidationError(str(ve.message_dict))
                else:
                    raise django_exceptions.ValidationError(ve.messages)
        else:
            raise django_exceptions.ValidationError(
                self.error_messages['invalid'] % getmeta(self.resource_type).resource_name, code='invalid')


class ResourceListField(ResourceField):
    """
    Form field that wraps a list of odin fields.
    """
    def to_python(self, value):
        if value is None or value == '':
            return

        if isinstance(value, (list, tuple)):
            return value

        if isinstance(value, six.string_types):
            try:
                return self.codec.loads(value, self.resource_type, full_clean=False)
            except odin_exceptions.CodecDecodeError as cde:
                raise django_exceptions.ValidationError(str(cde))
            except ValueError as ve:
                raise django_exceptions.ValidationError(str(ve))

        raise django_exceptions.ValidationError(
            self.error_messages['invalid'] % getmeta(self.resource_type).resource_name, code='invalid')

    def validate(self, value):
        if value is None:
            return

        elif isinstance(value, (list, tuple)):
            errors = {}
            for idx, resource in enumerate(value):
                try:
                    super(ResourceField, self).validate(value)
                except django_exceptions.ValidationError as ve:
                        errors[idx] = ve.message_dict
            if errors:
                raise django_exceptions.ValidationError(errors)

        # Unknown type
        else:
            raise django_exceptions.ValidationError(
                self.error_messages['invalid'] % getmeta(self.resource_type).resource_name, code='invalid'
            )
