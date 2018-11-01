"""Sentry integration to Muffin framework."""
import asyncio
import importlib
import sys

import raven
import raven_aiohttp
from muffin import HTTPException, to_coroutine
from muffin.plugins import BasePlugin


# Package information
# ===================

__version__ = "0.2.2"
__project__ = "muffin-sentry"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


class Plugin(BasePlugin):

    """Setup Sentry and send exceptions and messages."""

    name = 'sentry'
    client = None
    defaults = {
        'dsn': '',                  # Sentry DSN
        'catch_all': True,          # Catch all exceptions (enable Sentry middleware)
        'tags': None,               # Raven tags (See Raven docs for more)
        'raven_processors': None,   # Message processors (See Raven docs for more)
        'ignore': (HTTPException, asyncio.CancelledError),

        # List of async processors with takes request and app in context
        'processors': ('muffin_sentry.RequestProcessor',),

        'exclude_paths': None,  # Exclude request paths
    }
    processors = None

    def setup(self, app):
        """Initialize Sentry Client."""
        super().setup(app)

        if not self.cfg.dsn:
            return

        self.client = raven.Client(
            self.cfg.dsn, transport=raven_aiohttp.AioHttpTransport,
            exclude_paths=self.cfg.exclude_paths, processors=self.cfg.raven_processors,
            tags=self.cfg.tags, context={'app': app.name, 'sys.argv': sys.argv[:]})

    def startup(self, app):
        """Bind loop to transport."""
        if not self.client:
            return app.logger.warning('Sentry Client is not configured.')

        self.client.remote.options['loop'] = self.app.loop
        if self.cfg.catch_all:
            app.middlewares.insert(0, self._middleware)

        if self.cfg.processors:
            self.processors = []
            for P in self.cfg.processors:
                if isinstance(P, str):
                    try:
                        mod, klass = P.rsplit('.', 1)
                        mod = importlib.import_module(mod)
                        P = getattr(mod, klass)
                    except (ImportError, AttributeError):
                        self.app.logger.error('Invalid Sentry Processor: %s' % P)
                        continue
                P.process = to_coroutine(P.process)
                self.processors.append(P(self))

    async def _middleware(self, request, handler):
        try:
            return await handler(request)
        except self.cfg.ignore:
            raise
        except Exception:
            await self._captureException(sys.exc_info(), request=request)
            raise

    _middleware.__middleware_version__ = 1

    def captureException(self, *args, **kwargs):
        """Capture exception."""
        return asyncio.ensure_future(self._captureException(*args, **kwargs), loop=self.app.loop)

    def captureMessage(self, *args, **kwargs):
        """Capture message."""
        return asyncio.ensure_future(self._captureMessage(*args, **kwargs), loop=self.app.loop)

    async def _captureException(self, *args, request=None, data=None, **kwargs):
        """Send exception."""
        assert self.client, 'captureException called before the plugin configured'
        data = await self.prepareData(data, request)
        return self.client.captureException(*args, data=data, **kwargs)

    async def _captureMessage(self, *args, request=None, data=None, **kwargs):
        """Send message."""
        assert self.client, 'captureMessage called before the plugin configured'
        data = await self.prepareData(data, request)
        return self.client.captureMessage(*args, data=data, **kwargs)

    async def prepareData(self, data=None, request=None):
        """Data prepare before send it to Sentry."""
        data = data or {}
        if self.processors:
            for p in self.processors:
                data_ = await p.process(data, request=request)
                try:
                    data.update(data_)
                except TypeError:
                    self.app.logger.warn('Invalid processor response from %s' % p)

        return data


class Processor:

    """Base class for async processors.."""

    __slots__ = 'plugin',

    def __init__(self, plugin):
        """Store Sentry plugin in self."""
        self.plugin = plugin


class RequestProcessor(Processor):

    """Process request for Sentry."""

    async def process(self, data, request=None):  # noqa
        """Append request data to Sentry context."""
        if request is None:
            return {}

        data = {
            'request': {
                'url': "%s://%s%s" % (request.scheme, request.host, request.path),
                'query_string': request.query_string,
                'method': request.method,
                'headers': {k.title(): str(v) for k, v in request.headers.items()},
            }
        }

        data['request']['data'] = await request.read()

        return data
