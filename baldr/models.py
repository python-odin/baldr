# -*- coding: utf-8 -*-
import inspect
import odin
import sys

from django.core.exceptions import ValidationError
from django.db import models
from odin import registration
from odin.fields import NOT_PROVIDED
from odin.mapping import FieldResolverBase, mapping_factory
from odin.utils import getmeta

from baldr.model_fields import ResourceField, ResourceListField

try:
    from odin.codecs import msgpack_codec
except ImportError:
    msgpack_codec = None


# Register support for Django Models and Validators

class ModelFieldResolver(FieldResolverBase):
    """
    Field resolver for Django Models
    """
    def get_field_dict(self):
        meta = getmeta(self.obj)
        return {f.attname: f for f in meta.fields}

registration.register_field_resolver(ModelFieldResolver, models.Model)


# Register a the Django ValidationError exception with Odin.
def django_validation_error_handler(exception, field, errors):
    if hasattr(exception, 'code') and exception.code in field.error_messages:
        message = field.error_messages[exception.code]
        if exception.params:
            message = message % exception.params
        errors.append(message)
    else:
        errors.extend(exception.messages)

registration.register_validation_error_handler(ValidationError, django_validation_error_handler)


# Model factories and helper methods.

class ModelResourceMixin(odin.Resource):
    """
    Mixin that adds some helper methods for working with resources generated from models.
    """
    class Meta:
        abstract = True

    model = None

    @classmethod
    def from_model(cls, model, context=None, **field_values):
        """
        Convert this resource into a specified to resource.

        A mapping must be defined for conversion between this resource and to_resource or an exception will be raised.
        """
        mapping = registration.get_mapping(cls.model, cls)
        return mapping(model, context).convert(**field_values)

    @classmethod
    def from_queryset(cls, queryset, single=False):
        """
        Use a query set and optimise fetching of data. This assumes that your resource has the sames fields as the
        model. This helper uses ``values_list`` and ``only`` methods to limit data processing and create resources
        faster.

        The method is a lot faster than from a model as it does not construct a full model.

        :param queryset:
        :param single:
        :return:

        """
        fields = getmeta(cls).field_map.keys()
        data = queryset.values(*fields)
        if single:
            return cls.create_from_dict(data[0])
        else:
            return [cls.create_from_dict(d) for d in data]

    def save(self, context=None, commit=True, ignore_fields=None):
        """
        Save this resource instance to the database.

        :param context: Context dict passed to each mapping function.
        :param commit: If commit=True, then the newly created model instance will be saved to the database.
        :param ignore_fields: Fields that should be ignored in mapping
        :return: Newly created model instance.

        """
        model = self.convert_to(self.model, context, ignore_fields)
        if commit:
            model.save()
        return model

    def update(self, instance, context=None, commit=True, lazy=True):
        """
        Update an existing model from this model.

        :param instance: Model instance to be updated.
        :param context: Context dict passed to each mapping function.
        :param commit: If True, then changes to the updated model instance will be saved to the database.
        :param lazy: If True, then instance and source resource are compared, if no changes are found no database,
            operation is performed.
        :return: Updated model instance.

        """
        assert isinstance(instance, self.model)

        mapping = registration.get_mapping(self.__class__, self.model)
        mapper = mapping(self, context)

        if not lazy or len(mapper.diff(instance)) > 0:
            mapper.update(instance)
            if commit:
                instance.save()
        return instance


def default_map(field):
    if field.default is models.NOT_PROVIDED:
        return NOT_PROVIDED
    return field.default

BASIC_ATTR_MAP = dict(
    null='null',
    choices='choices',
    default=default_map,
    use_default_if_not_provided=lambda _: True
)
MODEL_FIELD_MAP = [
    # (Model Field, Odin Field, attribute mappings {odin_attr: model_attr})
    (ResourceField, odin.DictAs, dict(resource='resource_type', null='null')),
    (ResourceListField, odin.ListOf, dict(resource='resource_type', null='null')),

    (models.AutoField, odin.StringField, dict()),
    (models.DateTimeField, odin.DateTimeField, BASIC_ATTR_MAP),
    (models.TimeField, odin.TimeField, BASIC_ATTR_MAP),
    (models.URLField, odin.UrlField, BASIC_ATTR_MAP),
    (models.IntegerField, odin.IntegerField, BASIC_ATTR_MAP),
    (models.FloatField, odin.FloatField, BASIC_ATTR_MAP),
    (models.BooleanField, odin.BooleanField, BASIC_ATTR_MAP),
    (models.CharField, odin.StringField, dict(BASIC_ATTR_MAP, max_length='max_length')),
    (models.TextField, odin.StringField, BASIC_ATTR_MAP),
]


def field_factory(model_field):
    """
    Return an equivalent odin field from a Django model field.
    :param model_field:
    :return:
    """
    for mf, of, attrs in MODEL_FIELD_MAP:
        if isinstance(model_field, mf):
            attrs = {
                oa: (ma(model_field) if callable(ma) else getattr(model_field, ma))
                for oa, ma in attrs.items()
            }
            attrs['validators'] = getattr(model_field, 'validators')
            return of(**attrs)


NO_REVERSE_FIELDS = [
    # Model Field, check method
    (models.DateField, lambda f: f.auto_now_add or f.auto_now),
]


def field_in_filters(model_field, filters):
    """
    Check if a supplied model_field matches a set of filters.

    :param model_field:
    :param filters:
    :return:

    """
    for mf, filter_ in filters:
        if isinstance(model_field, mf):
            if filter_(model_field):
                return True
    return False


def model_resource_factory(model, module=None, base_resource=odin.Resource, resource_mixins=None,
                           exclude_fields=None, include_fields=None, generate_mappings=True,
                           return_mappings=False, additional_fields=None, resource_type_name=None,
                           reverse_exclude_fields=None):
    """
    Factory method for generating a resource from a existing Django model.

    Usage::

        class Person(models.Model):
            name = models.CharField(max_length=50)
            age = models.IntegerField()

        PersonResource = model_resource_factory(Person)

    :param model: The Django model to generate resource from.
    :param module: Module you want the class to be a member of; default uses the calling module. This value can be the
        name of another module (eg the __name__ field in a module).
    :param base_resource: Base resource to extend from; default is ``odin.Resource``.
    :param resource_mixins: Any additional mixin resources; default ``baldr.models.ModelResourceMixin``.
    :param exclude_fields: Any fields that should be excluded from the resource.
    :param include_fields: Explicitly define what fields that should be included on the resource.
    :param generate_mappings: Generate mappings between resource and model (in both directions).
    :param return_mappings: Return the mappings along with the model resource (returns a
        tuple(Resource, ForwardMapping, ReverseMapping).
    :param additional_fields: Any additional fields that should be appended to the resource, these can override fields
        from the model.
    :param resource_type_name: Name of the resource created by the factory (default is the name of the model)
    :param reverse_exclude_fields: Excluded fields from reverse mapping.

    """
    resource_mixins = resource_mixins or []
    bases = tuple(resource_mixins + [ModelResourceMixin, base_resource])
    attrs = {}
    model_opts = model._meta
    resource_type_name = resource_type_name or model_opts.object_name

    # Determine the calling module
    if module is None:
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])

    # Append fields
    exclude_fields = exclude_fields or []
    reverse_exclude_fields = reverse_exclude_fields or []
    for mf in model_opts.fields:
        if mf.attname in exclude_fields:
            continue

        # Create an odin version of the field.
        field = field_factory(mf)
        if field:
            attrs[mf.attname] = field

        # Check if the field should not be reversed
        if field_in_filters(mf, NO_REVERSE_FIELDS):
            reverse_exclude_fields.append(mf.attname)

    # Add any additional fields.
    if additional_fields:
        assert isinstance(additional_fields, dict)
        for attname, field in additional_fields.items():
            attrs[attname] = field

    # Setup other require attributes and create type
    if isinstance(module, str):
        module = sys.modules[module]
    attrs['__module__'] = module.__name__
    attrs['model'] = model
    resource_type = type(resource_type_name, bases, attrs)

    # Generate mappings
    forward_mapping, reverse_mapping = None, None
    if generate_mappings:
        forward_mapping, reverse_mapping = mapping_factory(
            model, resource_type, reverse_exclude_fields=reverse_exclude_fields
        )

    if return_mappings:
        return resource_type, forward_mapping, reverse_mapping
    else:
        return resource_type


# Register Django Promises (used by translated strings) with Odin codecs

# TODO: this is not quite correct, will be corrected in updated serialisation tools current in development
# for odin
# json_codec.JSON_TYPES[Promise] = force_text
# if msgpack_codec:
#     msgpack_codec.TYPE_SERIALIZERS[Promise] = force_text
