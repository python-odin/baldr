# -*- coding: utf-8 -*-
import odin


class Listing(odin.Resource):
    """
    Response for listing results. This includes offset, count support for
    paging etc.

    """
    class Meta:
        namespace = None

    # Wrapper to provide code completion
    def __init__(self, results, limit, offset=0, total_count=None):
        super(Listing, self).__init__(results, limit, offset, total_count)

    results = odin.ArrayField(
        help_text="The list of resources."
    )
    limit = odin.IntegerField(
        help_text="The resource limit in the result set."
    )
    offset = odin.IntegerField(
        default=0,
        help_text="The offset within the result set."
    )
    total_count = odin.IntegerField(
        null=True,
        help_text="The total number of items in the result set."
    )


class Error(odin.Resource):
    """
    Response returned for errors.

    The *meta* field should be utilised to provide additional information that
    is specific to the error. Eg if validation failed then meta would contain
    an object that maps field names to error messages.

    """
    class Meta:
        namespace = None

    status = odin.IntegerField(
        help_text="HTTP status code of the response."
    )
    sub_status = odin.IntegerField(
        help_text="Sub-status code for more fine grained error results."
    )
    message = odin.StringField(
        help_text="A message that can be used for an end user."
    )
    developer_message = odin.StringField(
        null=True,
        help_text="More complex error message suitable for a developer."
    )
    meta = odin.StringField(
        null=True,
        help_text="Additional meta information that can help to solve issues."
    )
