from __future__ import absolute_import
from django.shortcuts import get_object_or_404
from odin import registration
from . import ResourceApi, listing, create, detail, update, delete


class ModelResourceApi(ResourceApi):
    """
    Provides an API for working with Django models.

    This API assumes that mappings have been defined between between the model and a suitable resource.

    """
    # Model this API deals with
    model = None
    # Model field to use for single model queries.
    model_id_field = 'pk'
    # Mapping to use for mapping to model
    to_model_mapping = None
    # Mapping to use for mapping to resource
    to_resource_mapping = None

    def __init__(self, *args, **kwargs):
        super(ModelResourceApi, self).__init__(*args, **kwargs)

        assert self.model, "A model has not been provided."

        # Attempt to resolve mappings
        if self.to_model_mapping is None:
            self.to_model_mapping = registration.get_mapping(self.resource, self.model)
        if self.to_resource_mapping is None:
            self.to_resource_mapping = registration.get_mapping(self.model, self.resource)

    def get_queryset(self, request):
        return self.model.objects.all()

    def get_instance(self, request, resource_id):
        return get_object_or_404(self.get_queryset(request), **{
            self.model_id_field: resource_id
        })

    def save_model(self, request, instance, is_new=False):
        instance.save()
        return instance


class ListMixin(ModelResourceApi):
    """
    Mixin that provides a basic paged listing response.
    """
    @listing
    def object_list(self, request, limit, offset):
        queryset = self.get_queryset(request)
        results = queryset[offset:offset+limit]
        return self.to_resource_mapping.apply(results), len(queryset)


class CreateMixin(ModelResourceApi):
    """
    Mixin that provides a basic creation method.
    """
    @create
    def object_create(self, request):
        resource = self.resource_from_body(request)
        instance = self.to_model_mapping.apply(resource)
        instance.id = None
        self.save_model(request, instance, True)
        return self.to_resource_mapping.apply(instance), 201


class DetailMixin(ModelResourceApi):
    """
    Mixin that provides a basic full detail method.
    """
    @detail
    def object_detail(self, request, resource_id):
        instance = self.get_instance(request, resource_id)
        return self.to_resource_mapping.apply(instance)


class UpdateMixin(ModelResourceApi):
    """
    Mixin that provides a basic model update method.
    """
    @update
    def object_update(self, request, resource_id):
        instance = self.get_instance(request, resource_id)
        resource = self.resource_from_body(request)
        self.to_model_mapping(resource).update(instance, ignore_fields=('id', 'pk'))
        self.save_model(request, instance, False)
        return self.to_resource_mapping.apply(instance), 200


class DeleteMixin(ModelResourceApi):
    """
    Mixin that provides a basic delete method.
    """
    @delete
    def object_delete(self, request, resource_id):
        self.get_instance(request, resource_id).delete()
