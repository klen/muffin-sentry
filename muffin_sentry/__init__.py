"""Sentry integration to Muffin framework."""
from __future__ import annotations

from contextvars import ContextVar
from functools import partial
from typing import TYPE_CHECKING, Callable, ClassVar, Dict, List, Optional, TypeVar

from muffin import Application, Request, ResponseError, ResponseRedirect
from muffin.plugins import BasePlugin
from sentry_sdk import Hub
from sentry_sdk import Scope as SentryScope
from sentry_sdk import init as sentry_init
from sentry_sdk.tracing import Transaction

if TYPE_CHECKING:
    from asgi_tools.types import TASGIApp, TASGIReceive, TASGISend

TProcess = Callable[[Dict, Dict, Request], Dict]
TVProcess = TypeVar("TVProcess", bound=TProcess)


class Plugin(BasePlugin):
    """Setup Sentry and send exceptions and messages."""

    name = "sentry"
    client = None
    defaults: ClassVar[Dict] = {
        "dsn": "",  # Sentry DSN
        "transaction_style": "url",  # url | endpoint
        "sdk_options": {},  # See https://docs.sentry.io/platforms/python/configuration/options/
        "ignore_errors": (ResponseError, ResponseRedirect),
    }
    current_scope: ContextVar[Optional[SentryScope]] = ContextVar(
        "sentry_scope",
        default=None,
    )
    processors: List[TProcess]

    def __init__(self, *args, **kwargs):
        """Initialize the plugin."""
        super(Plugin, self).__init__(*args, **kwargs)
        self.processors = []

    def setup(self, app: Application, **options):
        """Initialize Sentry Client."""
        super().setup(app, **options)

        # Setup Sentry
        dsn = self.cfg.dsn
        if dsn:
            sentry_init(dsn=dsn, **self.cfg.sdk_options)

    async def middleware(  # type: ignore[override]
        self,
        handler: TASGIApp,
        request: Request,
        receive: TASGIReceive,
        send: TASGISend,
    ):
        """Capture exceptions to Sentry."""
        hub = Hub(Hub.current)
        cfg = self.cfg
        url = request.url
        scope = request.scope
        scope_type = scope["type"]
        transaction_style = cfg.transaction_style
        with hub.configure_scope() as sentry_scope:
            sentry_scope.clear_breadcrumbs()
            sentry_scope._name = "muffin"
            self.current_scope.set(sentry_scope)
            sentry_scope.add_event_processor(partial(self.process_data, request=request))
            trans_name = url.path
            if transaction_style == "endpoint":
                endpoint = scope.get("endpoint")
                trans_name = endpoint.__qualname__ if endpoint else trans_name

            trans = Transaction.continue_from_headers(
                request.headers,
                op=f"{scope_type}.muffin",
                name=trans_name,
                source=transaction_style,
            )
            trans.set_tag("asgi.type", scope_type)

            with hub.start_transaction(
                trans,
                custom_sampling_context={"asgi_scope": sentry_scope},
            ):
                try:
                    response = await handler(request, receive, send)
                    trans.set_http_status(response.status_code)
                    return response  # noqa: TRY300

                except Exception as exc:
                    if type(exc) not in cfg.ignore_errors:
                        hub.capture_exception(exc)
                    raise exc from None

    def processor(self, fn: TVProcess) -> TVProcess:
        """Register a custom processor."""
        self.processors.append(fn)
        return fn

    def process_data(self, event: Dict, hint: Dict, *, request: Request) -> Dict:
        """Prepare data before send it to Sentry."""
        if request:
            url = request.url
            scope = request.scope
            event["request"] = {
                "url": f"{url.scheme}://{url.host}{url.path}",
                "query_string": request.url.query_string,
                "method": scope["method"],
                "headers": dict(request.headers),
            }

            if scope.get("client"):
                event["request"]["env"] = {"REMOTE_ADDR": scope["client"][0]}

        for processor in self.processors:
            event = processor(event, hint, request)

        return event

    def capture_exception(self, *args, **kwargs):
        """Capture exception."""
        if self.cfg.dsn:
            with Hub(Hub.current, self.current_scope.get()) as hub:
                return hub.capture_exception(*args, **kwargs)
        return None

    def capture_message(self, *args, **kwargs):
        """Capture message."""
        if self.cfg.dsn:
            with Hub(Hub.current, self.current_scope.get()) as hub:
                return hub.capture_message(*args, **kwargs)
        return None
