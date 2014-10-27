# -*- coding: utf-8 -*-
from django.core.exceptions import ValidationError
from django.db import models
import sys
from odin import registration
import odin
from odin.mapping import FieldResolverBase, mapping_factory
from baldr.model_fields import ResourceField, ResourceListField


# Register support for Django Models and Validators

class ModelFieldResolver(FieldResolverBase):
    """
    Field resolver for Django Models
    """
    def get_field_dict(self):
        meta = self.obj._meta
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
        fields = cls._meta.field_map.keys()
        data = queryset.values(*fields)
        if single:
            return cls.create_from_dict(data[0])
        else:
            return [cls.create_from_dict(d) for d in data]

    def save(self, context=None, commit=True):
        """
        Save this resource instance to the database.

        :param context: Context dict passed to each mapping function.
        :param commit: If commit=True, then the newly created model instance will be saved to the database.
        :return: Newly created model instance.

        """
        model = self.convert_to(self.model, context)
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


MODEL_FIELD_MAP = [
    # (Model Field, Odin Field, attribute mappings {odin_attr: model_attr})
    (ResourceField, odin.DictAs, dict(resource='resource_type', null='null')),
    (ResourceListField, odin.ListOf, dict(resource='resource_type', null='null')),

    (models.DateTimeField, odin.DateTimeField, dict(null='null', choices='choices')),
    (models.DateField, odin.DateField, dict(null='null', choices='choices')),
    (models.TimeField, odin.TimeField, dict(null='null', choices='choices')),
    (models.URLField, odin.UrlField, dict(null='null', choices='choices')),
    (models.IntegerField, odin.IntegerField, dict(null='null', choices='choices')),
    (models.FloatField, odin.FloatField, dict(null='null', choices='choices')),
    (models.BooleanField, odin.BooleanField, dict(null='null', choices='choices')),
    (models.CharField, odin.StringField, dict(max_length='max_length', null='null', choices='choices')),
    (models.TextField, odin.StringField, dict(null='null', choices='choices')),
]


def field_factory(model_field):
    """
    Return an equivalent odin field from a Django model field.
    :param model_field:
    :return:
    """
    for mf, of, attrs in MODEL_FIELD_MAP:
        if isinstance(model_field, mf):
            attrs = {oa: getattr(model_field, ma) for oa, ma in attrs.items()}
            attrs['validators'] = getattr(model_field, 'validators')
            return of(**attrs)


def model_resource_factory(model, base_resource=odin.Resource, resource_mixins=None, module=None, exclude_fields=None,
                           include_fields=None, generate_mappings=True, return_mappings=False, additional_fields=None,
                           resource_type_name=None):
    """
    Factory method for generating a resource from a existing Django model.

    Usage::

        class Person(models.Model):
            name = models.CharField(max_length=50)
            age = models.IntegerField()

        PersonResource = model_resource_factory(Person)

    :param model: The Django model to generate resource from.
    :param base_resource: Base resource to extend from; default is ``odin.Resource``.
    :param resource_mixins: Any additional mixin resources; default ``baldr.models.ModelResourceMixin``.
    :param module: Module you want the class to be a member of; default is ``model.__module__``.
    :param exclude_fields: Any fields that should be excluded from the resource.
    :param include_fields: Explicitly define what fields that should be included on the resource.
    :param generate_mappings: Generate mappings between resource and model (in both directions).
    :param return_mappings: Return the mappings along with the model resource (returns a
        tuple(Resource, ForwardMapping, ReverseMapping).
    :param additional_fields: Any additional fields that should be appended to the resource, these can override fields
        from the model.
    :param resource_type_name: Name of the resource created by the factory (default is the name of the model)

    """
    resource_mixins = resource_mixins or []
    bases = tuple(resource_mixins + [ModelResourceMixin, base_resource])
    attrs = {}
    model_opts = model._meta
    resource_type_name = resource_type_name or model_opts.object_name

    # Append fields
    exclude_fields = exclude_fields or []
    for mf in model_opts.fields:
        if mf.attname in exclude_fields:
            continue

        # Create an odin version of the field.
        field = field_factory(mf)
        if field:
            attrs[mf.attname] = field

    # Add any additional fields.
    if additional_fields:
        assert isinstance(additional_fields, dict)
        for attname, field in additional_fields.items():
            attrs[attname] = field

    # Setup other require attributes and create type
    if isinstance(module, str):
        module = sys.modules[module]
    attrs['__module__'] = module or model.__module__
    attrs['model'] = model
    resource_type = type(resource_type_name, bases, attrs)

    # Generate mappings
    forward_mapping, reverse_mapping = None, None
    if generate_mappings:
        forward_mapping, reverse_mapping = mapping_factory(model, resource_type)

    if return_mappings:
        return resource_type, forward_mapping, reverse_mapping
    else:
        return resource_type
