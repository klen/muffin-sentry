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

__version__ = "0.2.0"
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

        except (HTTPException, asyncio.CancelledError):
            raise

        except Exception:
            yield from sentry.captureException(sys.exc_info(), request=request)
            raise

    return sentry_middleware


class Plugin(BasePlugin):

    """Setup Sentry and send exceptions and messages."""

    name = 'sentry'
    client = None
    defaults = {
        'dsn': '',              # Sentry DSN
        'catch_all': True,      # Catch all exceptions (enable Sentry middleware)
        'tags': None,           # Raven tags (See Raven docs for more)
        'raven_processors': None,     # Message processors (See Raven docs for more)

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

    def start(self, app):
        """Bind loop to transport."""
        if self.client:
            self.client.remote.options['loop'] = self.app.loop
            app.middlewares.insert(0, sentry_middleware_factory)

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

    def captureException(self, *args, **kwargs):
        """Capture exception."""
        return asyncio.ensure_future(self._captureException(*args, **kwargs), loop=self.app.loop)

    def captureMessage(self, *args, **kwargs):
        """Capture message."""
        return asyncio.ensure_future(self._captureMessage(*args, **kwargs), loop=self.app.loop)

    @asyncio.coroutine
    def _captureException(self, *args, request=None, data=None, **kwargs):
        """Send exception."""
        assert self.client, 'captureException called before the plugin configured'
        data = yield from self.prepareData(data, request)
        return self.client.captureException(*args, data=data, **kwargs)

    @asyncio.coroutine
    def _captureMessage(self, *args, request=None, data=None, **kwargs):
        """Send message."""
        assert self.client, 'captureMessage called before the plugin configured'
        data = yield from self.prepareData(data, request)
        return self.client.captureMessage(*args, data=data, **kwargs)

    @asyncio.coroutine
    def prepareData(self, data=None, request=None):
        """Data prepare before send it to Sentry."""
        data = data or {}
        if self.processors:
            for p in self.processors:
                data_ = yield from p.process(data, request=request)
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

    @asyncio.coroutine
    def process(self, data, request=None):  # noqa
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

        data['request']['data'] = yield from request.read()

        return data
