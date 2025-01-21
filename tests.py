from functools import partial
from importlib import metadata
from unittest import mock

import muffin
import pytest
import sentry_sdk
from asgi_tools import Request


@pytest.fixture
def app():
    return muffin.Application(SENTRY_DSN="http://public:secret@example.com/1")


@pytest.fixture
def sentry(app):
    import muffin_sentry

    version = metadata.version("muffin-sentry")
    return muffin_sentry.Plugin(
        app,
        transaction_style="endpoint",
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
    request = Request(client.build_scope("/", type="http", method="POST"), lambda: None, lambda: None)  # type: ignore[]
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
            "env": {
                "REMOTE_ADDR": "127.0.0.1",
            },
        },
    }


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
        res = await client.get("/error")
        assert res.status_code == 500
        assert mocked.called
        env, *_ = mocked.call_args.args[0]
        event = env.get_event()
        assert event["transaction"] == "/error"
        assert event["request"]
        assert event["request"]["url"] == "http://localhost/error"

        @app.route("/scope")
        async def scope(request):
            request["user"] = {"id": "1", "email": "test@test.com"}
            scope = sentry.current_scope.get()
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


# ruff: noqa: TRY002, ARG001
