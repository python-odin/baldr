# -*- coding: utf-8 -*-
from django.core.exceptions import ValidationError
from django.db import models
import odin
from odin import exceptions as odin_exceptions
from odin.codecs import json_codec
import six
from baldr import form_fields


class ResourceField(six.with_metaclass(models.SubfieldBase, models.TextField)):
    """Field that serializes/de-serializes a Odin resource to the
    database seamlessly."""
    def __init__(self, resource, *args, **kwargs):
        assert issubclass(resource, odin.Resource)
        self.resource = resource
        super(ResourceField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        if value is None or value == '':
            return self.resource()
        elif isinstance(value, six.string_types):
            try:
                return json_codec.loads(value, self.resource, False)
            except odin_exceptions.ValidationError as ve:
                raise ValidationError(message=ve.message_dict)
        else:
            return value

    def get_db_prep_save(self, value, connection):
        # Convert our JSON object to a string before we save
        if not isinstance(value, self.resource):
            return super(ResourceField, self).get_db_prep_save("", connection=connection)
        else:
            return super(ResourceField, self).get_db_prep_save(json_codec.dumps(value), connection=connection)

    def formfield(self, **kwargs):
        defaults = {
            'form_class': form_fields.ResourceField,
            'resource': self.resource
        }
        defaults.update(kwargs)
        return super(ResourceField, self).formfield(**defaults)

# Register field with south.
try:
    from south.modelsinspector import add_introspection_rules
    add_introspection_rules([], ["^baldr\.model_fields\.ResourceField"])
except ImportError:
    pass
