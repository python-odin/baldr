from django.shortcuts import get_object_or_404
from odin import registration
from odin.compatibility import deprecated
from baldr import api


@deprecated(message="Will be removed in 0.9 in favour of `baldr.api2.models.ModelResourceApi`.")
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
        super(ModelResourceApi, self).__init__(*args, **kwargs)

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


@deprecated(message="Will be removed in 0.9 in favour of `baldr.api2.models.ListMixin`.")
class ListModelMixin(api.ListMixin, ModelResourceApi):
    """
    Mixin for ``ModelResourceApi`` that fetches a list of resources from a database.
    """
    # Override of mapping for lists
    to_resource_list_mapping = None

    def list_resources(self, request, offset, limit):
        models = self.get_queryset(request)[offset:offset+limit]
        resource_mapping = self.to_resource_list_mapping or self.to_resource_mapping
        return resource_mapping.apply(models)


@deprecated(message="Will be removed in 0.9 in favour of `baldr.api2.models.CreateMixin`.")
class CreateModelMixin(api.CreateMixin, ModelResourceApi):
    """
    Mixin for ``ModelResourceApi`` that handles resource creation to a database.
    """
    def create_resource(self, request, resource, is_complete):
        new_model = self.to_model_mapping.apply(resource)
        new_model.pk = None
        self.save_model(request, new_model)
        return self.to_resource_mapping.apply(new_model), 201


@deprecated(message="Will be removed in 0.9 in favour of `baldr.api2.models.DetailMixin`.")
class RetrieveModelMixin(api.RetrieveMixin, ModelResourceApi):
    """
    Mixin for ``ModelResourceApi`` that handles resource retrieval from a database.
    """
    def retrieve_resource(self, request, resource_id):
        model = self.get_model(request, resource_id)
        return self.to_resource_mapping.apply(model)


@deprecated(message="Will be removed in 0.9 in favour of `baldr.api2.models.UpdateMixin`.")
class UpdateModelMixin(api.UpdateMixin, ModelResourceApi):
    """
    Mixin for ``ModelResourceApi`` that handles resource update to a database.
    """
    def update_resource(self, request, resource_id, resource, is_complete):
        if is_complete:
            model = self.to_model_mapping.apply(resource)
        else:
            model = self.get_model(request, resource_id)
            self.to_model_mapping(resource).update(model)
        setattr(model, self.model_id_field, resource_id)
        self.save_model(request, model)


@deprecated(message="Will be removed in 0.9 in favour of `baldr.api2.models.DeleteMixin`.")
class DeleteModelMixin(api.DeleteMixin, ModelResourceApi):
    def delete_resource(self, request, resource_id):
        self.get_model(request, resource_id).delete()
