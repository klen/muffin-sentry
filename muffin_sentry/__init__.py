"""Sentry integration to Muffin framework."""
from collections.abc import Callable
from contextvars import ContextVar
from functools import partial
from typing import Dict, List, Optional, TypeVar

from asgi_tools.types import TASGIApp, TASGIReceive, TASGISend
from muffin import Application, Request, ResponseError, ResponseRedirect
from muffin.plugins import BasePlugin
from sentry_sdk import Hub
from sentry_sdk import Scope as SentryScope
from sentry_sdk import init as sentry_init
from sentry_sdk.tracing import Transaction

# Package information
# ===================

__version__ = "1.3.0"
__project__ = "muffin-sentry"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


TProcess = Callable[[Dict, Dict, Request], Dict]
TVProcess = TypeVar("TVProcess", bound=TProcess)


class Plugin(BasePlugin):

    """Setup Sentry and send exceptions and messages."""

    name = "sentry"
    client = None
    defaults = {
        "dsn": "",  # Sentry DSN
        "sdk_options": {},  # See https://docs.sentry.io/platforms/python/configuration/options/
        "ignore_errors": (ResponseError, ResponseRedirect),
    }
    current_scope: ContextVar[Optional[SentryScope]] = ContextVar(
        "sentry_scope", default=None
    )
    processors: List[TProcess]

    def __init__(self, *args, **kwargs):
        """Initialize the plugin."""
        super(Plugin, self).__init__(*args, **kwargs)
        self.processors = []

    def setup(self, app: Application, **options):
        """Initialize Sentry Client."""
        super().setup(app, **options)

        if not self.cfg.dsn:
            return

        # Setup Sentry
        sentry_init(dsn=self.cfg.dsn, **self.cfg.sdk_options)

    async def middleware(  # type: ignore
        self,
        handler: TASGIApp,
        request: Request,
        receive: TASGIReceive,
        send: TASGISend,
    ):
        """Capture exceptions to Sentry."""
        hub = Hub(Hub.current)
        with hub.configure_scope() as scope:
            scope.clear_breadcrumbs()
            scope._name = "muffin"
            self.current_scope.set(scope)
            scope.add_event_processor(partial(self.processData, request=request))

            with hub.start_transaction(
                Transaction.continue_from_headers(
                    request.headers, op=f"{request.scope['type']}.muffin"
                ),
                custom_sampling_context={"asgi_scope": scope},
            ):
                try:
                    return await handler(request, receive, send)

                except Exception as exc:
                    if type(exc) not in self.cfg.ignore_errors:
                        hub.capture_exception(exc)
                    raise exc from None

    def processor(self, fn: TVProcess) -> TVProcess:
        """Register a custom processor."""
        self.processors.append(fn)
        return fn

    def processData(self, event: Dict, hint: Dict, request: Request) -> Dict:
        """Prepare data before send it to Sentry."""
        if request:
            url = request.url
            event["request"] = {
                "url": f"{url.scheme}://{url.host}{url.path}",
                "query_string": request.url.query_string,
                "method": request.method,
                "headers": dict(request.headers),
            }

            if request.get("client"):
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
