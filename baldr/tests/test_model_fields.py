from django.core.exceptions import ValidationError
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

    def test_invalid_values(self):
        target = SimpleModel(simple='{"$":"baldr.tests.SimpleResource}',
                             simple_list=123)
        self.assertEqual('{"$":"baldr.tests.SimpleResource}', target.simple)
        self.assertEqual(123, target.simple_list)

    def test_empty_field(self):
        target = SimpleModel(simple=None, simple_list='')
        self.assertIsNone(target.simple)
        self.assertIsNone(target.simple_list)

        target = SimpleModel(simple={}, simple_list='{}')
        self.assertIsNone(target.simple)
        self.assertIsNone(target.simple_list)


class ResourceFieldTestCase(unittest.TestCase):
    def test_to_python(self):
        target = model_fields.ResourceField(resource_type=SimpleResource)

        self.assertEqual(None, target.to_python(None))
        self.assertEqual(None, target.to_python(''))
        self.assertEqual(None, target.to_python({}))
        self.assertEqual(None, target.to_python('{}'))
        resource = SimpleResource(name='foo')
        self.assertEqual('foo', target.to_python(resource).name)
        self.assertEqual('bar', target.to_python('{"$":"baldr.tests.SimpleResource", "name": "bar"}').name)
        self.assertRaises(ValidationError, target.to_python, 123)
