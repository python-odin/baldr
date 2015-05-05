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
        super().__init__(*args, **kwargs)

        assert self.model, "A model has not been provided."

        # Attempt to resolve mappings
        if self.to_model_mapping is None:
            self.to_model_mapping = registration.get_mapping(self.resource, self.model)
        if self.to_resource_mapping is None:
            self.to_resource_mapping = registration.get_mapping(self.model, self.resource)

    def get_queryset(self, request):
        return self.model.objects.all()

    def get_model(self, request, resource_id):
        return get_object_or_404(self.get_queryset(request), **{
            self.model_id_field: resource_id
        })

    def save_model(self, request, model):
        model.save()


class ListMixin(ModelResourceApi):
    @listing
    def object_list(self, request, limit, offset):
        queryset = self.get_queryset(request)
        results = queryset[offset:offset+limit]
        return self.to_resource_mapping.apply(results), len(queryset)


class CreateMixin(ModelResourceApi):
    @create
    def object_create(self, request):
        pass


class DetailMixin(ModelResourceApi):
    @detail
    def object_detail(self, request, resource_id):
        instance = self.get_model(request, resource_id)
        return self.to_resource_mapping.apply(instance)


class UpdateMixin(ModelResourceApi):
    @update
    def object_update(self, request, resource_id):
        pass


class DeleteMixin(ModelResourceApi):
    @delete
    def object_delete(self, request, resource_id):
        self.get_model(request, resource_id).delete()
