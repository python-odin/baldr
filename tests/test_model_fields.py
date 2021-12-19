import odin
import pytest

from django.core.exceptions import ValidationError
from django.db import models
from baldr import model_fields


class SimpleResource(odin.Resource):
    class Meta:
        namespace = "baldr.tests"

    name = odin.StringField()


class SimpleModel(models.Model):
    class Meta:
        app_label = "test"

    simple = model_fields.ResourceField(resource_type=SimpleResource)
    simple_list = model_fields.ResourceListField(resource_type=SimpleResource)


class TestResourceFieldDescriptor:
    def test_valid_values(self):
        target = SimpleModel(
            simple=SimpleResource(name="foo"),
            simple_list='[{"$":"baldr.tests.SimpleResource", "name": "bar"}]',
        )

        assert target.simple.name == "foo"
        assert target.simple_list[0].name == "bar"

    def test_invalid_values(self):
        target = SimpleModel(
            simple='{"$":"baldr.tests.SimpleResource}', simple_list=123
        )
        assert target.simple == '{"$":"baldr.tests.SimpleResource}'
        assert target.simple_list == 123

    def test_empty_field(self):
        target = SimpleModel(simple=None, simple_list="")
        assert target.simple is None
        assert target.simple_list is None

        target = SimpleModel(simple={}, simple_list="{}")
        assert target.simple is None
        assert target.simple_list is None


class TestResourceField:
    def test_to_python(self):
        target = model_fields.ResourceField(resource_type=SimpleResource)

        assert target.to_python(None) is None
        assert target.to_python("") is None
        assert target.to_python({}) is None
        assert target.to_python("{}") is None

        resource = SimpleResource(name="foo")
        assert target.to_python(resource).name == "foo"
        assert (
            target.to_python('{"$":"baldr.tests.SimpleResource", "name": "bar"}').name
            == "bar"
        )

        with pytest.raises(ValidationError):
            target.to_python(123)
