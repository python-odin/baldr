# -*- coding: utf-8 -*-
from __future__ import absolute_import

__version__ = "0.5.1"
default_app_config = 'baldr.BaldrAppConfig'


def _ensure_registration():
    """
    Ensure that model type resolvers and validation tools are registered with Odin.

    This provides support for Django Models and use of Django Validators in Odin resources.
    """
    from . import models
_ensure_registration()
