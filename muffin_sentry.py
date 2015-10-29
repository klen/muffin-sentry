"""Sentry integration to Muffin framework."""
import asyncio

import raven
import raven_aiohttp
import sys
import importlib
from muffin import HTTPException, to_coroutine
from muffin.plugins import BasePlugin


# Package information
# ===================

__version__ = "0.0.7"
__project__ = "muffin-sentry"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


@asyncio.coroutine
def sentry_middleware_factory(app, handler):
    """Create middleware for Sentry plugin."""
    sentry = app.ps.sentry

    @asyncio.coroutine
    def sentry_middleware(request):
        """Catch unhandled exceptions during request."""
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
    """Prepare data for Sentry from aiohttp.Request."""
    data = {}
    if request.method in ('POST', 'PUT', 'PATCH') and request._post is None:
        data = yield from request.post()

    return {
        'url': "%s://%s%s" % (request.scheme, request.host, request.path),
        'query_string': request.query_string,
        'method': request.method,
        'headers': {k.title(): str(v) for k, v in request.headers.items()},
        'data': dict(data),
    }


class Plugin(BasePlugin):

    """Setup Sentry and send exceptions and messages."""

    name = 'sentry'
    client = None
    defaults = {
        'dsn': '',              # Sentry DSN
        'catch_all': True,      # Catch all exceptions (enable Sentry middleware)
        'tags': None,           # Raven tags (See Raven docs for more)
        'processors': None,     # Message processors (See Raven docs for more)
        'async_processors': None,  # List of async processors with takes request in context
        'exclude_paths': None,  # Exclude request paths
    }
    async_processors = None

    def setup(self, app):
        """Initialize Sentry Client."""
        super().setup(app)

        if not self.cfg.dsn:
            return

        self.client = raven.Client(
            self.cfg.dsn, transport=raven_aiohttp.AioHttpTransport,
            exclude_paths=self.cfg.exclude_paths, processors=self.cfg.processors,
            tags=self.cfg.tags, context={'app': app.name, 'sys.argv': sys.argv[:]})

        if self.cfg.async_processors:
            self.async_processors = []
            for P in self.cfg.async_processors:
                if isinstance(P, str):
                    try:
                        mod, klass = P.rsplit('.', 1)
                        mod = importlib.import_module(mod)
                        P = getattr(mod, klass)
                    except (ImportError, AttributeError):
                        self.app.logger.error('Invalid Sentry Processor: P')
                        continue
                P.process = to_coroutine(P.process)
                self.async_processors.append(P(self.client))

    def start(self, app):
        """Bind loop to transport."""
        if self.client:
            self.client.remote.options['loop'] = self.app.loop
            app.middlewares.insert(0, sentry_middleware_factory)

    @asyncio.coroutine
    def captureException(self, *args, request=None, data=None, **kwargs):
        """Send exception."""
        assert self.client, 'captureException called before the plugin configured'
        data = yield from self.prepareData(data, request)
        return self.client.captureException(*args, data=data, **kwargs)

    @asyncio.coroutine
    def captureMessage(self, *args, request=None, data=None, **kwargs):
        """Send message."""
        assert self.client, 'captureMessage called before the plugin configured'
        data = yield from self.prepareData(data, request)
        return self.client.captureMessage(*args, data=data, **kwargs)

    @asyncio.coroutine
    def prepareData(self, data=None, request=None):
        """Data prepare before send it to Sentry."""
        data = data or {}
        if request is not None:
            data['request'] = yield from request_to_data(request)

        if self.async_processors:
            for p in self.async_processors:
                data_ = yield from p.process(data, request=request)
                data.update(data_)

        return data
