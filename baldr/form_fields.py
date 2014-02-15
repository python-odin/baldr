# -*- coding: utf-8 -*-
from django.core import exceptions as django_exceptions
from django.forms import widgets
from django.forms.fields import Field
from django.utils.translation import ugettext_lazy as _
import odin
from odin import exceptions as odin_exceptions
from odin.codecs import json_codec


class ResourceField(Field):
    """
    Form field that validates a resource.
    """
    widget = widgets.Textarea

    default_error_messages = {
        'invalid': _('This field is not a valid %s resource.'),
    }

    def __init__(self, resource, indent=4, *args, **kwargs):
        super(ResourceField, self).__init__(*args, **kwargs)
        self.resource = resource
        self.indent = indent

    def prepare_value(self, value):
        if isinstance(value, odin.Resource):
            return json_codec.dumps(value, indent=self.indent)
        return value

    def to_python(self, value):
        try:
            return json_codec.loads(value, self.resource, full_clean=False)
        except odin_exceptions.ValidationError as ve:
            raise django_exceptions.ValidationError(str(ve.message_dict))
        except ValueError as ve:
            raise django_exceptions.ValidationError(ve.message)

    def validate(self, value):
        super(ResourceField, self).validate(value)

        if value in self.empty_values:
            return

        if not isinstance(value, self.resource):
            raise django_exceptions.ValidationError(
                self.error_messages['invalid'] % self.resource._meta.name, code='invalid')

        try:
            value.full_clean()
        except odin_exceptions.ValidationError as ve:
            raise django_exceptions.ValidationError(ve.message_dict)
