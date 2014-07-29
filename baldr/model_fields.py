# -*- coding: utf-8 -*-
from django.core import exceptions as django_exceptions
from django.db import models
from odin import exceptions as odin_exceptions
from odin.codecs import json_codec
import six
from baldr import form_fields


class ResourceField(six.with_metaclass(models.SubfieldBase, models.TextField)):
    """Field that serializes/de-serializes an Odin resource to the database seamlessly."""
    form_class = form_fields.ResourceField

    def __init__(self, resource_type, codec=json_codec, *args, **kwargs):
        super(ResourceField, self).__init__(*args, **kwargs)
        self.resource_type = resource_type
        self.codec = codec

    def to_python(self, value):
        if value in [None, '', {}, '{}']:  # Treat an empty JSON object as null.
            return

        if isinstance(value, self.resource_type):
            return value

        if isinstance(value, six.string_types):
            return self.codec.loads(value, self.resource_type, full_clean=False)

        raise django_exceptions.ValidationError(
            'Value provide is not a valid %s resource' % self.resource_type._meta.resource_name)

    def validate(self, value, model_instance):
        if not self.editable:
            # Skip validation for non-editable fields.
            return

        if value is None and not self.null:
            raise django_exceptions.ValidationError(self.error_messages['null'], code='null')

        if not self.blank and value in self.empty_values:
            raise django_exceptions.ValidationError(self.error_messages['blank'], code='blank')

        if isinstance(value, self.resource_type):
            try:
                value.full_clean()
            except odin_exceptions.ValidationError as ve:
                raise django_exceptions.ValidationError(ve.message_dict)

        raise django_exceptions.ValidationError(
            'Value provide is not a valid %s resource' % self.resource_type._meta.resource_name)

    def get_db_prep_save(self, value, connection):
        # Convert our JSON object to a string before we save
        if value is None:
            value = None if self.null else ""
        else:
            value = json_codec.dumps(value)
        return super(ResourceField, self).get_db_prep_save(value, connection=connection)

    def formfield(self, **kwargs):
        defaults = {
            'form_class': self.form_class,
            'resource_type': self.resource_type
        }
        defaults.update(kwargs)
        return super(ResourceField, self).formfield(**defaults)


class ResourceListField(ResourceField):
    """Field that serializes/de-serializes a list of Odin resource to the database seamlessly."""
    form_class = form_fields.ResourceListField

    def to_python(self, value):
        if value in [None, '', {}, '{}']:  # Treat an empty JSON object as null.
            return

        if isinstance(value, (list, tuple)):
            return value

        if isinstance(value, six.string_types):
            try:
                return self.codec.loads(value, self.resource_type, full_clean=False)
            except odin_exceptions.ValidationError as ve:
                raise django_exceptions.ValidationError(str(ve.message_dict))
            except ValueError as ve:
                raise django_exceptions.ValidationError(ve.message)

        raise django_exceptions.ValidationError(
            'Value provide is not a valid %s resource' % self.resource_type._meta.resource_name)

    def validate(self, value, model_instance):
        if not self.editable:
            # Skip validation for non-editable fields.
            return

        if value is None and not self.null:
            raise django_exceptions.ValidationError(self.error_messages['null'], code='null')

        if not self.blank and value in self.empty_values:
            raise django_exceptions.ValidationError(self.error_messages['blank'], code='blank')

        if isinstance(value, (list, tuple)):
            errors = {}
            for idx, resource in enumerate(value):
                try:
                    super(ResourceField, self).validate(value, model_instance)
                except django_exceptions.ValidationError as ve:
                        errors[idx] = ve.message_dict
            if errors:
                raise django_exceptions.ValidationError(errors)

        else:
            raise django_exceptions.ValidationError(
                'Value provide is not a valid %s resource' % self.resource_type._meta.resource_name)


# Register field with south.
try:
    from south.modelsinspector import add_introspection_rules
    add_introspection_rules([
        (
            [ResourceField, ResourceListField],
            [],
            {
                'resource_type': ['resource_type', {}],
                'codec': ['codec', {'default': json_codec}],
            }
        )
    ], ["^baldr\.model_fields\.\w+Field"])
except ImportError:
    pass
