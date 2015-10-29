"""Example application."""

import muffin


class Processor:

    """Example async processor."""

    def __init__(self, client):
        """Store client."""
        self.client = client

    def process(self, data, request=None):  # noqa
        """Process data."""
        extra = data.get('extra', {})
        extra['test'] = 'passed'
        return {'extra': extra}


app = muffin.Application(
    'sentry',

    PLUGINS=('muffin_sentry',),
    SENTRY_DSN='',  # noqa
    SENTRY_ASYNC_PROCESSORS=('example.Processor',)

)


@app.register('/')
def exception(request):
    """Raise unhandled exception here."""
    raise ValueError('Test exception')
