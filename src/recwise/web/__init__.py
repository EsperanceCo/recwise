"""Local review web app, bound to 127.0.0.1 only. See web.cli for the entry point."""

from recwise.web.app import create_app

__all__ = ["create_app"]
