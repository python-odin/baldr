from django.forms.forms import DeclarativeFieldsMetaclass, BaseForm
import six


class ResourceFormMetaclass(DeclarativeFieldsMetaclass):
    pass


class BaseResourceForm(BaseForm):
    pass


class ResourceForm(six.with_metaclass(ResourceFormMetaclass, BaseResourceForm)):
    pass
