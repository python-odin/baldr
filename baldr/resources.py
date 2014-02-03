# -*- coding: utf-8 -*-
import odin


class HttpError(odin.Resource):
    """
    Response returned for errors
    """
    status = odin.IntegerField()
    code = odin.IntegerField()
    message = odin.StringField()
    developer_message = odin.StringField(null=True)
    meta = odin.StringField(null=True)

    class Meta:
        namespace = None
