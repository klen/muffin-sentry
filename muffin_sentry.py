""" Sentry integration for Muffin framework. """
import asyncio

import raven
import raven_aiohttp
import sys
from muffin import HTTPException
from muffin.plugins import BasePlugin


# Package information
# ===================

__version__ = "0.0.4"
__project__ = "muffin-sentry"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


class Plugin(BasePlugin):

    """ Connect to Async Mongo. """

    name = 'sentry'
    defaults = {
        'dsn': '',
        'tags': None,
        'processors': None,
        'exclude_paths': None,
    }

    def setup(self, app):
        """ Initialize Sentry Client. """
        super().setup(app)

        self.client = raven.Client(
            self.options.dsn, transport=raven_aiohttp.AioHttpTransport,
            exclude_paths=self.options.exclude_paths, processors=self.options.processors,
            tags=self.options.tags, context={'app': app.name, 'sys.argv': sys.argv[:]})

    def start(self, app):
        """ Bind loop to transport. """
        self.client.remote.options['loop'] = self.app.loop

    @asyncio.coroutine
    def _get_data_from_request(self, request):

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

    @asyncio.coroutine
    def middleware_factory(self, app, handler):
        """ Catch exceptions. """
        @asyncio.coroutine
        def middleware(request):
            try:
                response = yield from handler(request)
                return response

            except HTTPException as exc:
                raise exc

            except Exception as exc:
                if self.options.dsn:
                    exc_info = sys.exc_info()
                    data = yield from self._get_data_from_request(request)
                    self.client.captureException(exc_info, data=data)
                raise exc

        return middleware

    @asyncio.coroutine
    def captureException(self, *args, request=None, data=None, **kwargs):
        """ Send exception. """
        assert self.client, 'captureException called before the plugin configured'
        if not data and request:
            data = yield from self._get_data_from_request(request)
        return self.client.captureException(*args, data=data, **kwargs)

    @asyncio.coroutine
    def captureMessage(self, *args, request=None, data=None, **kwargs):
        """ Send message. """
        assert self.client, 'captureMessage called before the plugin configured'
        if not data and request is not None:
            data = yield from self._get_data_from_request(request)
        return self.client.captureMessage(*args, data=data, **kwargs)
