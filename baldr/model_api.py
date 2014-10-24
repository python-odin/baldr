from django.shortcuts import get_object_or_404
from odin import registration
from baldr import api


class ModelResourceApi(api.ResourceApi):
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


class ListModelMixin(api.ListMixin, ModelResourceApi):
    def list_resources(self, request, offset, limit):
        models = self.get_queryset(request)[offset:offset+limit]
        return self.to_resource_mapping.apply(models)


class CreateModelMixin(api.CreateMixin, ModelResourceApi):
    def create_resource(self, request, resource, is_complete):
        new_model = self.to_model_mapping.apply(resource)
        new_model.pk = None
        new_model.save()
        return self.to_resource_mapping.apply(new_model), 201


class RetrieveModelMixin(api.RetrieveMixin, ModelResourceApi):
    def retrieve_resource(self, request, resource_id):
        model = self.get_model(request, resource_id)
        return self.to_resource_mapping.apply(model)


class UpdateModelMixin(api.UpdateMixin, ModelResourceApi):
    def update_resource(self, request, resource_id, resource, is_complete):
        if is_complete:
            model = self.to_model_mapping.apply(resource)
        else:
            model = self.get_model(request, resource_id)
            self.to_model_mapping(resource).update(model)
        model.pk = resource_id
        model.save()


class DeleteModelMixin(api.DeleteMixin, ModelResourceApi):
    def delete_resource(self, request, resource_id):
        self.get_model(request, resource_id).delete()
