"""Sentry integration to Muffin framework."""
import typing as t
from contextvars import ContextVar
from functools import partial

from asgi_tools.typing import Receive, Send, ASGIApp
from muffin import ResponseError, ResponseRedirect, Application, Request
from muffin.plugins import BasePlugin
from sentry_sdk import init as sentry_init, Hub, Scope as SentryScope
from sentry_sdk.tracing import Transaction


# Package information
# ===================

__version__ = "1.0.0"
__project__ = "muffin-sentry"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


TPROCESSOR = t.Callable[[t.Dict, t.Dict, Request], t.Dict]
TVPROCESSOR = t.TypeVar('TVPROCESSOR', bound=TPROCESSOR)


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

    def __init__(self, *args, **kwargs):
        """Initialize the plugin."""
        super(Plugin, self).__init__(*args, **kwargs)
        self.processors: t.List[TPROCESSOR] = []

    def setup(self, app: Application, **options):
        """Initialize Sentry Client."""
        super().setup(app, **options)

        if not self.cfg.dsn:
            return

        # Setup Sentry
        sentry_init(dsn=self.cfg.dsn, **self.cfg.sdk_options)

        # Install the middleware
        app.middleware(self.__middleware)

    async def __middleware(self, handler: ASGIApp, request: Request, receive: Receive, send: Send):
        """Capture exceptions to Sentry."""
        hub = Hub(Hub.current)
        with hub.configure_scope() as scope:
            scope.clear_breadcrumbs()
            scope._name = "muffin"
            self.current_scope.set(scope)
            scope.add_event_processor(partial(self.processData, request=request))

            with hub.start_transaction(Transaction.continue_from_headers(
                        request.headers, op=f"{request.scope['type']}.muffin"),
                        custom_sampling_context={'asgi_scope': scope}
                    ):
                try:
                    return await handler(request, receive, send)

                except Exception as exc:
                    if type(exc) not in self.cfg.ignore_errors:
                        hub.capture_exception(exc)
                    raise exc from None

    def processor(self, fn: TVPROCESSOR) -> TVPROCESSOR:
        """Register a custom processor."""
        self.processors.append(fn)
        return fn

    def processData(self, event: t.Dict, hint: t.Dict, request: Request) -> t.Dict:
        """Prepare data before send it to Sentry."""
        if request:
            url = request.url
            event['request'] = {
                'url': f"{url.scheme}://{url.host}{url.path}",
                'query_string': request.url.query_string,
                'method': request.method,
                'headers': dict(request.headers),
            }

            if request.get('client'):
                event["request"]["env"] = {"REMOTE_ADDR": request.client[0]}

        for processor in self.processors:
            event = processor(event, hint, request)

        return event

    def captureException(self, *args, **kwargs):
        """Capture exception."""
        with Hub(Hub.current, self.current_scope.get()) as hub:
            return hub.capture_exception(*args, **kwargs)

    def captureMessage(self, *args, **kwargs):
        """Capture message."""
        with Hub(Hub.current, self.current_scope.get()) as hub:
            return hub.capture_message(*args, **kwargs)
