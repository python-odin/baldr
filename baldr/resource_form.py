# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six
import odin

from collections import OrderedDict
from django.forms import fields
from django.forms.forms import DeclarativeFieldsMetaclass, BaseForm
from django.forms.utils import ErrorList
from odin.exceptions import ValidationError
from odin.utils import getmeta

ALL_FIELDS = '__all__'

NO_OP = lambda v: v

# Common field options
COMMON_OPTIONS = (
    ('null', lambda v: not bool(v), 'required'),
    # ('verbose_name', lambda v: v.capitalize(), 'label'),
    ('doc_text', NO_OP, 'help_text'),
)
CHOICE_OPTOINS = (
    ('choices', NO_OP, 'choices'),
)

FORM_FIELD_MAP = {
    odin.DateTimeField: (fields.DateTimeField, None),
    odin.DateField: (fields.DateField, None),
    odin.TimeField: (fields.TimeField, None),
    odin.HttpDateTimeField: (fields.DateTimeField, None),
    odin.TimeStampField: (fields.DateTimeField, None),
    odin.UrlField: (fields.URLField, None),
    odin.IntegerField: (fields.IntegerField, None),
    odin.FloatField: (fields.FloatField, None),
    odin.BooleanField: (fields.BooleanField, None),
    odin.StringField: (fields.CharField, (('max_length', NO_OP, 'max_length'),)),
}


def construct_instance(form, instance, fields=None, exclude=None):
    opts = instance._meta

    cleaned_data = form.cleaned_data
    for f in opts.fields:
        if fields is not None and f.name not in fields:
            continue
        if exclude and f.name in exclude:
            continue

        f.value_to_object(instance, cleaned_data[f.name])

    return instance


def construct_field(field, **kwargs):
    if field.choices:
        form_field = fields.ChoiceField
        field_options = CHOICE_OPTOINS
    else:
        try:
            form_field, field_options = FORM_FIELD_MAP[field.__class__]
        except KeyError:
            return

    option_values = {ff: t(getattr(field, rf)) for rf, t, ff in COMMON_OPTIONS}
    if field_options:
        option_values.update((ff, t(getattr(field, rf))) for rf, t, ff in field_options)
    option_values.update(kwargs)
    return form_field(**option_values)


def fields_for_resource(resource, fields=None, exclude=None, widgets=None,
                        resourcefield_callback=None, localized_fields=None,
                        labels=None, help_texts=None, error_messages=None):
    field_list = []
    ignored = []
    opts = getmeta(resource)

    for f in opts.all_fields:
        if fields is not None and f.name not in fields:
            continue
        if exclude and f.name in exclude:
            continue

        kwargs = {}
        if widgets and f.name in widgets:
            kwargs['widget'] = widgets[f.name]
        if localized_fields == ALL_FIELDS or (localized_fields and f.name in localized_fields):
            kwargs['localize'] = True
        if labels and f.name in labels:
            kwargs['label'] = labels[f.name]
        if help_texts and f.name in help_texts:
            kwargs['help_text'] = help_texts[f.name]
        if error_messages and f.name in error_messages:
            kwargs['error_messages'] = error_messages[f.name]

        if resourcefield_callback is None:
            formfield = construct_field(f, **kwargs)
        elif not callable(resourcefield_callback):
            raise TypeError('resourcefield_callback must be a function or callable')
        else:
            formfield = resourcefield_callback(f, **kwargs)

        if formfield:
            field_list.append((f.name, formfield))
        else:
            ignored.append(f.name)

    field_dict = OrderedDict(field_list)
    if fields:
        field_dict = OrderedDict(
            ((f, field_dict.get(f)) for f in fields
             if ((not exclude) or (exclude and f not in exclude)) and (f not in ignored))
        )
    return field_dict


class ResourceFormOptions(object):
    def __init__(self, options=None):
        self.resource = getattr(options, 'resource', None)
        self.fields = getattr(options, 'fields', None)
        self.exclude = getattr(options, 'exclude', None)
        self.widgets = getattr(options, 'widgets', None)
        self.localized_fields = getattr(options, 'localized_fields', None)
        self.labels = getattr(options, 'labels', None)
        self.help_texts = getattr(options, 'help_texts', None)
        self.error_messages = getattr(options, 'error_messages', None)


class ResourceFormMetaclass(DeclarativeFieldsMetaclass):
    """
    Metaclass that collects Fields declared on the base classes.
    """
    def __new__(mcs, name, bases, attrs):
        resourcefield_callback = attrs.pop('resourcefield_callback', None)

        new_class = super(ResourceFormMetaclass, mcs).__new__(mcs, name, bases, attrs)

        if bases == (BaseResourceForm,):
            return new_class

        opts = new_class._meta = ResourceFormOptions(getattr(new_class, 'Meta', None))

        for opt in ['fields', 'exclude']:
            value = getattr(opts, opt)
            if isinstance(value, six.string_types) and value != ALL_FIELDS:
                msg = (
                    "%(resource)s.Meta.%(opt)s cannot be a string. "
                    "Did you mean to type: ('%(value)s',)?" % {
                        'resource': new_class.__name__, 'opt': opt, 'value': value,
                    }
                )
                raise TypeError(msg)

        if opts.resource:
            if opts.fields == ALL_FIELDS:
                opts.fields = None

            fields = fields_for_resource(opts.resource, opts.fields, opts.exclude,
                                         opts.widgets, resourcefield_callback,
                                         opts.localized_fields, opts.labels,
                                         opts.help_texts, opts.error_messages)

            fields.update(new_class.declared_fields)
        else:
            fields = new_class.declared_fields

        new_class.base_fields = fields

        return new_class


class BaseResourceForm(BaseForm):
    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None,
                 initial=None, error_class=ErrorList, label_suffix=None,
                 empty_permitted=False, instance=None):
        opts = self._meta
        if opts.resource is None:
            raise ValueError('ResourceForm has no resource class specified.')
        if instance is None:
            # if we didn't get an instance, instantiate a new one
            self.instance = opts.resource()
            object_data = {}
        else:
            self.instance = instance
            object_data = instance.as_dict()
        # if initial was provided, it should override the values from instance
        if initial is not None:
            object_data.update(initial)

        super(BaseResourceForm, self).__init__(data, files, auto_id, prefix, object_data,
                                               error_class, label_suffix, empty_permitted)

    def _update_errors(self, errors):
        self.add_error(None, errors)

    def _post_clean(self):
        opts = self._meta

        self.instance = construct_instance(self, self.instance, opts.fields, opts.exclude)

        try:
            self.instance.full_clean()
        except ValidationError as e:
            self._update_errors(e)


class ResourceForm(six.with_metaclass(ResourceFormMetaclass, BaseResourceForm)):
    pass
