import nox
from nox.sessions import Session


@nox.session(python=("3.6", "3.8"), reuse_venv=True)
@nox.parametrize("django", ["2.2"])
def tests(session: Session, django):
    session.install("odin", f"django=={django}")
    session.install("pytest", "pytest-cov", "pytest-django")
    session.env["PYTHONPATH"] = "tests:src"
    session.run("pytest")
