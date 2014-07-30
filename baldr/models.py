# -*- coding: utf-8 -*-
from django.db import models
from odin import registration, Resource
from odin.mapping import FieldResolverBase


class ModelFieldResolver(FieldResolverBase):
    """
    Field resolver for Django Models
    """
    def get_field_dict(self):
        return {f.attname: f for f in self.obj._meta.fields}

registration.register_field_resolver(ModelFieldResolver, models.Model)
