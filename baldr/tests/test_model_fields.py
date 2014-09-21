from django.db import models
import unittest
import odin
from baldr import model_fields


class SimpleResource(odin.Resource):
    class Meta:
        namespace = 'baldr.tests'
    name = odin.StringField()


class SimpleModel(models.Model):
    simple = model_fields.ResourceField(resource_type=SimpleResource)
    simple_list = model_fields.ResourceListField(resource_type=SimpleResource)


class ResourceFieldDescriptorTestCase(unittest.TestCase):
    def test_valid_values(self):
        target = SimpleModel(simple=SimpleResource(name="foo"),
                             simple_list='[{"$":"baldr.tests.SimpleResource", "name": "bar"}]')
        self.assertEqual("foo", target.simple.name)
        self.assertEqual("bar", target.simple_list[0].name)

    def test_empty_field(self):
        target = SimpleModel(simple=None, simple_list='')
        self.assertIsNone(target.simple)
        self.assertIsNone(target.simple_list)

        target = SimpleModel(simple={}, simple_list='{}')
        self.assertIsNone(target.simple)
        self.assertIsNone(target.simple_list)
