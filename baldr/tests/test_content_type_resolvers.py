from __future__ import absolute_import
from django import test
from django.test.client import RequestFactory
from .. import content_type_resolvers


class ContentTypeResolvers(test.TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_accepts_header_no_header(self):
        request = self.factory.get('/api/foo/')
        target = content_type_resolvers.accepts_header()
        actual = target(request)
        self.assertIsNone(actual)

    def test_accepts_header_json_header(self):
        request = self.factory.get('/api/foo/', accepts='application/json')
        target = content_type_resolvers.accepts_header()
        actual = target(request)
        self.assertEqual('application/json', actual)
