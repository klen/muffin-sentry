"""Sentry integration to Muffin framework."""
from contextvars import ContextVar
from functools import partial
import typing as t

from asgi_tools._types import Receive, Send
from asgi_tools.middleware import ASGIApp
from muffin import ResponseError, ResponseRedirect, Application, Request
from muffin.plugin import BasePlugin
from sentry_sdk import init as sentry_init, Hub as SentryHub, Scope as SentryScope


# Package information
# ===================

__version__ = "0.5.3"
__project__ = "muffin-sentry"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


class Plugin(BasePlugin):

    """Setup Sentry and send exceptions and messages."""

    name = 'sentry'
    client = None
    defaults = {
        'dsn': '',          # Sentry DSN
        'sdk_options': {},  # See https://docs.sentry.io/platforms/python/configuration/options/
        'ignore_errors': (ResponseError, ResponseRedirect),
    }
    current_scope: ContextVar[t.Optional[SentryScope]] = ContextVar('sentry_scope', default=None)

    def setup(self, app: Application, **options):
        """Initialize Sentry Client."""
        super().setup(app, **options)

        if not self.cfg.dsn:
            return

        # Setup Sentry
        sentry_init(dsn=self.cfg.dsn)

        # Install the middleware
        app.middleware(self.__middleware)

    async def __middleware(self, handler: ASGIApp, request: Request, receive: Receive, send: Send):
        """Capture exceptions to Sentry."""
        with SentryHub(SentryHub.current) as hub:
            with hub.configure_scope() as scope:
                self.current_scope.set(scope)
                processor = partial(self.prepareData, request=request)
                scope.add_event_processor(processor)

                try:
                    return await handler(request, receive, send)

                except Exception as exc:
                    if type(exc) not in self.cfg.ignore_errors:
                        hub.capture_exception(exc)
                    raise

    def prepareData(self, event: t.Dict, hint: t.Dict, request: Request = None) -> t.Dict:
        """Prepare data before send it to Sentry."""
        if request:
            event['request'] = {
                'url': "%s://%s%s" % (request.url.scheme, request.url.host, request.url.path),
                'query_string': request.url.query_string,
                'method': request.method,
                'headers': dict(request.headers),
            }

            if request.get('client'):
                event["request"]["env"] = {"REMOTE_ADDR": request.client[0]}

        return event

    def captureException(self, *args, **kwargs):
        """Capture exception."""
        with SentryHub(SentryHub.current, self.current_scope.get()) as hub:
            return hub.capture_exception(*args, **kwargs)

    def captureMessage(self, *args, **kwargs):
        """Capture message."""
        with SentryHub(SentryHub.current, self.current_scope.get()) as hub:
            return hub.capture_message(*args, **kwargs)
