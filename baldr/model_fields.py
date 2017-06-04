# -*- coding: utf-8 -*-
import six

from django.core import exceptions as django_exceptions
from django.db import models
from odin import exceptions as odin_exceptions
from odin.codecs import json_codec
from odin.utils import getmeta

from baldr import form_fields

# Treat an empty JSON object as None.
EMPTY_VALUES = (None, '', {}, '{}')


class ResourceFieldDescriptor(object):
    """
    Descriptor for use with a resource field.
    """
    def __init__(self, field):
        self.field = field

    def __get__(self, instance, owner):
        if instance is None:
            raise AttributeError(
                "The '%s' attribute can only be accessed from %s instances."
                % (self.field.name, owner.__name__))

        resource = instance.__dict__[self.field.name]

        if resource in EMPTY_VALUES:
            return

        if isinstance(resource, six.string_types):
            try:
                resource = self.field.codec.loads(resource, self.field.resource_type, full_clean=False)
            except (odin_exceptions.ValidationError, odin_exceptions.CodecDecodeError):
                pass
            else:
                instance.__dict__[self.field.name] = resource

        return resource

    def __set__(self, instance, value):
        instance.__dict__[self.field.name] = value


class ResourceField(models.TextField):
    """
    Improved resource field to handle serializes/de-serializes of an Odin resource.

    This improved field is lazy in that it will not attempt to de-serialise until needed.

    This new field is also compatible with Django 1.7 migrations.
    """
    form_class = form_fields.ResourceField

    def __init__(self, resource_type, verbose_name=None, name=None, allow_subclasses=True, *args, **kwargs):
        super(ResourceField, self).__init__(verbose_name, name, *args, **kwargs)
        self.resource_type = resource_type
        self.allow_subclasses = allow_subclasses
        # This is fixed for now, this is a limitation of the current odin codecs, a refactor is needed to provide
        # codec classes.
        self.codec = json_codec
        self.codec_kwargs = dict(sort_keys=True)

    def to_python(self, value):
        if value in EMPTY_VALUES:
            return

        if isinstance(value, self.resource_type):
            return value

        if isinstance(value, six.string_types):
            try:
                return self.codec.loads(value, self.resource_type, full_clean=False)
            except odin_exceptions.CodecDecodeError as cde:
                raise django_exceptions.ValidationError(str(cde))

        raise django_exceptions.ValidationError(
            'Value provide is not a valid %s resource' % getmeta(self.resource_type).resource_name)

    def validate(self, value, model_instance):
        if not self.editable:
            # Skip validation for non-editable fields.
            return

        if value is None and not self.null:
            raise django_exceptions.ValidationError(self.error_messages['null'], code='null')

        if not self.blank and value in self.empty_values:
            raise django_exceptions.ValidationError(self.error_messages['blank'], code='blank')

        if value.__class__ is self.resource_type or (self.allow_subclasses and isinstance(value, self.resource_type)):
            try:
                value.full_clean()
            except odin_exceptions.ValidationError as ve:
                raise django_exceptions.ValidationError(str(ve.message_dict))

        else:
            raise django_exceptions.ValidationError(
                'Value provide is not a valid %s resource' % getmeta(self.resource_type).resource_name)

    def get_db_prep_save(self, value, connection):
        # Convert our JSON object to a string before we save
        if value is None:
            value = None if self.null else ""
        else:
            value = self.codec.dumps(value, **self.codec_kwargs)
        return super(ResourceField, self).get_db_prep_save(value, connection=connection)

    def contribute_to_class(self, cls, name):
        super(ResourceField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, ResourceFieldDescriptor(self))

    def deconstruct(self):
        name, path, args, kwargs = super(ResourceField, self).deconstruct()
        kwargs['resource_type'] = self.resource_type
        # kwargs['codec'] = self.codec
        return name, path, args, kwargs

    def formfield(self, **kwargs):
        defaults = {
            'form_class': self.form_class,
            'resource_type': self.resource_type
        }
        defaults.update(kwargs)
        return super(ResourceField, self).formfield(**defaults)


class ResourceListField(ResourceField):
    """
    Field that serializes/de-serializes a list of Odin resource to the database seamlessly.
    """
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
            'Value provide is not a valid %s resource' % getmeta(self.resource_type).resource_name)

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
                'Value provide is not a valid %s resource' % getmeta(self.resource_type).resource_name)
