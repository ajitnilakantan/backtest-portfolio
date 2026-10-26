"""Dash application factory and compatibility accessors."""


def create_app():
    from .gui import app

    return app


def get_server():
    return create_app().server


def run():
    import logging

    from .config import CONFIG

    logging.basicConfig(level=logging.DEBUG if CONFIG.debug else logging.INFO)
    create_app().run(host=CONFIG.host, port=CONFIG.port, debug=CONFIG.debug)


__all__ = ["create_app", "get_server", "run"]
