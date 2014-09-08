# -*- coding: utf-8 -*-
from django.db import models
import sys
from odin import registration
import odin
from odin.mapping import FieldResolverBase, mapping_factory


class ModelFieldResolver(FieldResolverBase):
    """
    Field resolver for Django Models
    """
    def get_field_dict(self):
        meta = self.obj._meta
        return {f.attname: f for f in meta.fields}

registration.register_field_resolver(ModelFieldResolver, models.Model)


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
    # (Model Field, Odin Field, attribute mappings)
    (models.DateTimeField, odin.DateTimeField, {}),
    (models.DateField, odin.DateField, {}),
    (models.TimeField, odin.TimeField, {}),
    (models.URLField, odin.UrlField, {}),
    (models.IntegerField, odin.IntegerField, {}),
    (models.FloatField, odin.FloatField, {}),
    (models.BooleanField, odin.BooleanField, {}),
    (models.CharField, odin.StringField, {}),
]


def field_factory(model_field):
    """
    Return an equivalent odin field from a Django model field.
    :param model_field:
    :return:
    """
    for mf, of, m in MODEL_FIELD_MAP:
        if isinstance(model_field, mf):
            return of()


def model_resource_factory(model, base_resource=odin.Resource, resource_mixins=None, module=None,
                           exclude_fields=None, include_fields=None, generate_mappings=True, return_mappings=False):
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

    """
    bases = tuple(resource_mixins or [] + [ModelResourceMixin, base_resource])
    attrs = {}
    model_opts = model._meta

    # Append fields
    exclude_fields = exclude_fields or []
    for mf in model_opts.fields:
        if mf.attname in exclude_fields:
            continue

        # Create an odin version of the field.
        field = field_factory(mf)
        if field:
            attrs[mf.attname] = field

    # Setup other require attributes and create type
    if isinstance(module, str):
        module = sys.modules[module]
    attrs['__module__'] = module or model.__module__
    attrs['model'] = model
    resource_type = type(model_opts.object_name, bases, attrs)

    # Generate mappings
    forward_mapping, reverse_mapping = mapping_factory(model, resource_type) if generate_mappings else None, None

    if return_mappings:
        return resource_type, forward_mapping, reverse_mapping
    else:
        return resource_type
