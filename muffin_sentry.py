""" Sentry integration for Muffin framework. """
import asyncio

import raven
import raven_aiohttp
import sys
from muffin import HTTPException
from muffin.plugins import BasePlugin


# Package information
# ===================

__version__ = "0.0.6"
__project__ = "muffin-sentry"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


@asyncio.coroutine
def sentry_middleware_factory(app, handler):
    """ Catch exceptions. """
    sentry = app.ps.sentry

    @asyncio.coroutine
    def sentry_middleware(request):
        try:
            return (yield from handler(request))

        except HTTPException:
            raise

        except Exception:
            yield from sentry.captureException(sys.exc_info(), request=request)
            raise

    return sentry_middleware


@asyncio.coroutine
def request_to_data(request):
    """ Get Sentry data from Request. """
    data = {}
    if request.method in ('POST', 'PUT', 'PATCH') and request._post is None:
        data = yield from request.post()

    data = {
        'request': {
            'url': "http://%s%s" % (request.host, request.path),
            'query_string': request.query_string,
            'method': request.method,
            'headers': {k.title(): str(v) for k, v in request.headers.items()},
            'data': dict(data),
        }
    }
    return data


class Plugin(BasePlugin):

    """ Connect to Async Mongo. """

    name = 'sentry'
    defaults = {
        'dsn': '',              # Sentry DSN
        'catch_all': True,      # Catch all exceptions (enable Sentry middleware)
        'tags': None,           # Raven tags (See Raven docs for more)
        'processors': None,     # Message processors (See Raven docs for more)
        'exclude_paths': None,  # Exclude request paths
    }

    def setup(self, app):
        """ Initialize Sentry Client. """
        super().setup(app)

        self.client = None

        if self.options.dsn:
            self.client = raven.Client(
                self.options.dsn, transport=raven_aiohttp.AioHttpTransport,
                exclude_paths=self.options.exclude_paths, processors=self.options.processors,
                tags=self.options.tags, context={'app': app.name, 'sys.argv': sys.argv[:]})

    def start(self, app):
        """ Bind loop to transport. """
        if self.client:
            self.client.remote.options['loop'] = self.app.loop
            app.middlewares.insert(0, sentry_middleware_factory)

    @asyncio.coroutine
    def captureException(self, *args, request=None, data=None, **kwargs):
        """ Send exception. """
        assert self.client, 'captureException called before the plugin configured'
        if not data and request:
            data = yield from request_to_data(request)
        return self.client.captureException(*args, data=data, **kwargs)

    @asyncio.coroutine
    def captureMessage(self, *args, request=None, data=None, **kwargs):
        """ Send message. """
        assert self.client, 'captureMessage called before the plugin configured'
        if not data and request is not None:
            data = yield from request_to_data(request)
        return self.client.captureMessage(*args, data=data, **kwargs)
