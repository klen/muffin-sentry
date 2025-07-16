"""Sentry integration for the Muffin ASGI framework."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Callable, ClassVar, TypeVar

from muffin import Application, Request, Response, ResponseError, ResponseRedirect
from muffin.plugins import BasePlugin
from sentry_sdk import Scope as SentryScope
from sentry_sdk import (
    capture_exception,
    capture_message,
    get_current_scope,
    push_scope,
    start_session,
    start_transaction,
)
from sentry_sdk import init as sentry_init
from sentry_sdk.tracing import Transaction
from sentry_sdk.types import Event, Hint

if TYPE_CHECKING:
    from asgi_tools.types import TASGIApp, TASGIReceive, TASGISend

TProcess = Callable[[Event, Hint, Request], Event | None]
TVProcess = TypeVar("TVProcess", bound=TProcess)


class Plugin(BasePlugin):
    """Sentry plugin for Muffin."""

    name = "sentry"
    defaults: ClassVar = {
        "dsn": "",
        "sdk_options": {
            "traces_sample_rate": 0.1,  # Default tracing
            "profiles_sample_rate": 0.0,  # Disable profiling by default
        },
        "ignore_errors": (ResponseError, ResponseRedirect),
    }
    processors: list[TProcess]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processors = []

    def setup(self, app: Application, **options):
        """Initialize Sentry SDK."""
        if not super().setup(app, **options):
            return False

        dsn = self.cfg.dsn
        if dsn:
            sentry_init(dsn=dsn, **self.cfg.sdk_options)

        return True

    @property
    def scope(self) -> SentryScope:
        """Access the current scope."""
        return get_current_scope()

    async def middleware(  # type: ignore[override]
        self,
        handler: TASGIApp,
        request: Request,
        receive: TASGIReceive,
        send: TASGISend,
    ):
        """Sentry middleware to capture exceptions and trace requests."""
        cfg = self.cfg
        url = request.url
        scope = request.scope
        asgi_type = scope["type"]

        with push_scope() as sentry_scope:
            sentry_scope.clear_breadcrumbs()
            sentry_scope.set_tag("framework", "muffin")
            sentry_scope.set_tag("asgi.type", asgi_type)
            sentry_scope.add_event_processor(partial(self.process_data, request=request))

            start_session()

            trans = Transaction.continue_from_headers(
                request.headers,
                name=url.path,
                source="url",
                op=f"{asgi_type}.server",
            )

            with start_transaction(trans, custom_sampling_context={"asgi_scope": scope}):
                try:
                    response = await handler(request, receive, send)
                    trans.set_http_status(response.status_code)

                except Exception as exc:
                    trans.set_http_status(exc.status_code if isinstance(exc, Response) else 500)
                    if type(exc) not in cfg.ignore_errors:
                        capture_exception(exc)

                    raise

                else:
                    return response

    def processor(self, fn: TVProcess) -> TVProcess:
        """Register an event processor."""
        self.processors.append(fn)
        return fn

    def process_data(self, event: Event, hint: Hint, *, request: Request) -> Event | None:
        """Enhance Sentry event with request data and run processors."""
        if request:
            url = request.url
            scope = request.scope

            event["request"] = {
                "url": str(url),
                "query_string": url.query_string,
                "method": scope.get("method", ""),
                "headers": dict(request.headers),
            }

            if client := scope.get("client"):
                event["request"]["env"] = {"REMOTE_ADDR": client[0]}

        for processor in self.processors:
            event = processor(event, hint, request) or event

        return event

    def capture_exception(self, *args, **kwargs):
        """Manually capture an exception."""
        if self.cfg.dsn:
            return capture_exception(*args, **kwargs)

    def capture_message(self, *args, **kwargs):
        """Manually capture a message."""
        if self.cfg.dsn:
            return capture_message(*args, **kwargs)
