"""Sentry integration to Muffin framework."""

from __future__ import annotations

from contextvars import ContextVar
from functools import partial
from typing import TYPE_CHECKING, Callable, ClassVar, Optional, TypeVar

from muffin import Application, Request, ResponseError, ResponseRedirect
from muffin.plugins import BasePlugin
from sentry_sdk import Scope as SentryScope
from sentry_sdk import init as sentry_init
from sentry_sdk import isolation_scope, start_transaction
from sentry_sdk.sessions import track_session
from sentry_sdk.tracing import Transaction
from sentry_sdk.types import Event, Hint

if TYPE_CHECKING:
    from asgi_tools.types import TASGIApp, TASGIReceive, TASGISend

TProcess = Callable[[Event, Hint, Request], Optional[Event]]
TVProcess = TypeVar("TVProcess", bound=TProcess)

SENTRY_SCOPE: ContextVar[Optional[SentryScope]] = ContextVar("sentry_scope", default=None)


class CurrentScope:
    def __getattr__(self, name):
        scope = SENTRY_SCOPE.get()
        if scope:
            return getattr(scope, name)
        raise RuntimeError("Sentry scope is not available")


SCOPE = CurrentScope()


class Plugin(BasePlugin):
    """Setup Sentry and send exceptions and messages."""

    name = "sentry"
    client = None
    defaults: ClassVar = {
        "dsn": "",  # Sentry DSN
        "sdk_options": {},  # See https://docs.sentry.io/platforms/python/configuration/options/
        "ignore_errors": (ResponseError, ResponseRedirect),
    }
    processors: list[TProcess]

    def __init__(self, *args, **kwargs):
        """Initialize the plugin."""
        super(Plugin, self).__init__(*args, **kwargs)
        self.processors = []

    @property
    def current_scope(self):
        """Get current Sentry Scope."""
        return SENTRY_SCOPE

    def setup(self, app: Application, **options):
        """Initialize Sentry Client."""
        if not super().setup(app, **options):
            return False

        # Setup Sentry
        dsn = self.cfg.dsn
        if dsn:
            sentry_init(dsn=dsn, **self.cfg.sdk_options)

        return True

    async def middleware(  # type: ignore[override]
        self,
        handler: TASGIApp,
        request: Request,
        receive: TASGIReceive,
        send: TASGISend,
    ):
        """Capture exceptions to Sentry."""
        cfg = self.cfg
        url = request.url
        asgi_scope = request.scope
        asgi_type = asgi_scope["type"]

        with isolation_scope() as sentry_scope:
            with track_session(sentry_scope, session_mode="request"):
                sentry_scope.clear_breadcrumbs()
                sentry_scope._name = "muffin"
                sentry_scope.add_event_processor(partial(self.process_data, request=request))
                SENTRY_SCOPE.set(sentry_scope)

            trans = Transaction.continue_from_headers(
                request.headers,
                name=url.path,
                source="url",
                op=f"{asgi_type}.server",
            )
            trans.set_tag("asgi.type", asgi_type)
            with start_transaction(trans, custom_sampling_context={"asgi_scope": asgi_scope}):
                try:
                    response = await handler(request, receive, send)
                    trans.set_http_status(response.status_code)
                    return response  # noqa: TRY300

                except Exception as exc:
                    if type(exc) not in cfg.ignore_errors:
                        sentry_scope.capture_exception(exc)
                    raise exc from exc

    def processor(self, fn: TVProcess) -> TVProcess:
        """Register a custom processor."""
        self.processors.append(fn)
        return fn

    def process_data(self, event: Event, hint: Hint, *, request: Request) -> Optional[Event]:
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
            event = processor(event, hint, request) or event

        return event

    def capture_exception(self, *args, **kwargs):
        """Capture exception."""
        if self.cfg.dsn:
            scope = SENTRY_SCOPE.get()
            assert scope
            return scope.capture_exception(*args, **kwargs)

    def capture_message(self, *args, **kwargs):
        """Capture message."""
        if self.cfg.dsn:
            scope = SENTRY_SCOPE.get()
            assert scope
            return scope.capture_message(*args, **kwargs)
