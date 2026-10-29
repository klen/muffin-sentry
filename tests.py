from functools import partial
from importlib import metadata
from unittest import mock

import muffin
import pytest
import sentry_sdk
from asgi_tools import Request, ResponseWebSocket
from asgi_tools.tests import ASGITestClient


@pytest.fixture
def app():
    return muffin.Application(SENTRY_DSN="http://public:secret@example.com/1")


@pytest.fixture
def sentry(app):
    import muffin_sentry

    version = metadata.version("muffin-sentry")
    return muffin_sentry.Plugin(
        app,
        sdk_options={
            "environment": "tests",
            "release": version,
        },
    )


def test_global_scope(sentry):
    sentry_scope = sentry_sdk.get_global_scope()
    assert sentry_scope.client.options["release"]
    assert sentry_scope.client.options["environment"] == "tests"


def test_request_processor(sentry, client):
    scope = client.build_scope("/", type="http", method="POST")
    request = Request(scope, lambda: None, lambda: None)
    processor = partial(sentry.process_data, request=request)
    assert processor

    event = processor({}, {})
    assert event
    assert event == {
        "request": {
            "method": "POST",
            "query_string": "",
            "url": "http://localhost/",
            "headers": {
                "host": "localhost",
                "user-agent": "ASGI-Tools-Test-Client",
            },
        },
    }


def test_request_processor_pii(app, client):
    import muffin_sentry

    sentry = muffin_sentry.Plugin(app, sdk_options={"send_default_pii": True})
    scope = client.build_scope("/", type="http", method="POST")
    request = Request(scope, lambda: None, lambda: None)
    event = sentry.process_data({}, {}, request=request)
    assert event["request"]["env"] == {"REMOTE_ADDR": "127.0.0.1"}


async def test_success(app, sentry, client):

    @app.route("/success")
    async def success(request):
        return "OK"

    res = await client.get("/success")
    assert res.status_code == 200


async def test_muffin_sentry(app, client, sentry):

    @app.route("/error")
    async def error(request):
        raise Exception("Unhandled exception")

    @app.middleware
    async def md(handler, request, receive, send):
        """Test middleware errors."""
        if "md_error" in request.query:
            raise Exception("from middleware")
        return await handler(request, receive, send)

    @sentry.processor
    def user(event, hint, request):
        scope = request.scope
        if "user" in scope:
            event["user"] = scope["user"]
        return event

    await app.lifespan.run("startup")

    with mock.patch("sentry_sdk.transport.HttpTransport.capture_envelope") as mocked:
        trace_id = "1234567890abcdef1234567890abcdef"
        res = await client.get("/error", headers={"sentry-trace": f"{trace_id}-1234567890abcdef-1"})
        assert res.status_code == 500
        assert mocked.called
        env, *_ = mocked.call_args.args[0]
        event = env.get_event()
        assert event["transaction"] == f"{error.__module__}.{error.__qualname__}"
        assert event["contexts"]["trace"]["trace_id"] == trace_id
        assert event["request"]
        assert event["request"]["url"] == "http://localhost/error"

        @app.route("/scope")
        async def scope(request):
            request["user"] = {"id": "1", "email": "test@test.com"}
            scope = sentry.scope
            scope.set_tag("tests", "passed")
            app.plugins["sentry"].capture_message("tests")
            return "OK"

        res = await client.get("/scope")
        assert res.status_code == 200
        assert mocked.called
        env, *_ = mocked.call_args.args[0]
        event = env.get_event()
        assert event["user"]
        assert event["tags"]
        assert event["request"]

        mocked.reset_mock()

        res = await client.get("/success?md_error=1")
        assert res.status_code == 500
        assert mocked.called
        env, *_ = mocked.call_args.args[0]
        event = env.get_event()
        assert event["exception"]["values"][0]["mechanism"]


def test_manual_capture(sentry):
    with mock.patch("sentry_sdk.transport.HttpTransport.capture_envelope") as mocked:
        try:
            raise RuntimeError("Manual exception")
        except Exception as exc:
            sentry.capture_exception(exc)

        sentry.capture_message("Manual message")

        assert mocked.call_count >= 2

        envelope = mocked.call_args_list[-1].args[0]
        event = envelope.get_event()
        assert event.get("message") == "Manual message"


# ruff: noqa: TRY002, TRY301, BLE001


async def test_websocket(app, sentry, client):
    """Websocket handlers return nothing, the middleware must not expect a response."""

    @app.route("/ws")
    async def ws(request):
        async with ResponseWebSocket(request) as socket:
            await socket.send("hello")

    with mock.patch("sentry_sdk.transport.HttpTransport.capture_envelope") as mocked:
        async with client.websocket("/ws") as socket:
            assert await socket.receive() == "hello"

        events = [
            item.payload.json
            for call in mocked.call_args_list
            for item in call.args[0].items
            if item.headers.get("type") == "event"
        ]
        assert not events


async def test_sessions(app, sentry, client):
    """Every request sends one session, otherwise release health stays empty."""

    @app.route("/session")
    async def session(request):
        return "OK"

    with mock.patch.object(sentry_sdk.client.Client, "capture_session") as mocked:
        res = await client.get("/session")
        assert res.status_code == 200
        assert mocked.call_count == 1


async def test_not_found(app, client):
    """A 404 is not an error: no event, transaction status is the real one."""
    import muffin_sentry

    muffin_sentry.Plugin(app, sdk_options={"traces_sample_rate": 1.0})

    with mock.patch("sentry_sdk.transport.HttpTransport.capture_envelope") as mocked:
        res = await client.get("/missing")
        assert res.status_code == 404

        items = [item for call in mocked.call_args_list for item in call.args[0].items]
        assert not [item for item in items if item.headers.get("type") == "event"]
        transactions = [
            item.payload.json for item in items if item.headers.get("type") == "transaction"
        ]
        assert transactions[0]["contexts"]["trace"]["status"] == "not_found"


async def test_transaction_name(app, client):
    """Transactions are named after the view, not after the URL, so ids don't split them."""
    import muffin_sentry

    muffin_sentry.Plugin(app, sdk_options={"traces_sample_rate": 1.0})

    @app.route("/users/{id}")
    async def user(request):
        return "OK"

    with mock.patch("sentry_sdk.transport.HttpTransport.capture_envelope") as mocked:
        await client.get("/users/1")
        await client.get("/users/2")

        names = {
            item.payload.json["transaction"]
            for call in mocked.call_args_list
            for item in call.args[0].items
            if item.headers.get("type") == "transaction"
        }
        assert names == {f"{user.__module__}.{user.__qualname__}"}


async def test_without_dsn():
    """No DSN: the plugin is a thin no-op."""
    import muffin_sentry

    sentry_sdk.init()  # no dsn -> inactive client
    app = muffin.Application()
    sentry = muffin_sentry.Plugin(app)

    @app.route("/ok")
    async def ok(request):
        return "OK"

    with mock.patch("sentry_sdk.transport.HttpTransport.capture_envelope") as mocked:
        res = await ASGITestClient(app).get("/ok")
        assert res.status_code == 200
        assert not mocked.called
        assert sentry.capture_exception(RuntimeError("boom")) is None
        assert sentry.capture_message("hi") is None


def test_setup_contract(app):
    """The plugin follows the muffin 3 setup() contract."""
    from muffin_sentry import Plugin

    assert Plugin(app) is not None
    assert Plugin().setup(app) is True
    assert Plugin().setup(app, disabled=True) is False
