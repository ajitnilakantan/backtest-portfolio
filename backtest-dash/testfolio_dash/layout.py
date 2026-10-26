"""Layout access kept separate for integrations and future component composition."""


def get_layout():
    from app import app

    return app.layout
