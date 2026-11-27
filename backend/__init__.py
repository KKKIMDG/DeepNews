"""Backend package; importing batch tools must not start the API."""

__all__ = ["app"]


def __getattr__(name):
    if name == "app":
        from .main import app
        return app
    raise AttributeError(name)
