default_app_config = 'baldr.app.BaldrAppConfig'


def _ensure_registration():
    """
    Ensure that model type resolvers and validation tools are registered with Odin.

    This provides support for Django Models and use of Django Validators in Odin resources.
    """
    from . import models  # NoQA


_ensure_registration()
