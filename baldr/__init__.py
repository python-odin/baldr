# -*- coding: utf-8 -*-
from __future__ import absolute_import

__version__ = "0.8.dev0"
default_app_config = 'baldr.app.BaldrAppConfig'


def _ensure_registration():
    """
    Ensure that model type resolvers and validation tools are registered with Odin.

    This provides support for Django Models and use of Django Validators in Odin resources.
    """
    from . import models  # NoQA
_ensure_registration()
