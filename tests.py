from importlib import metadata
from unittest import mock

import muffin
import pytest


@pytest.fixture()
def app():
    import muffin_sentry

    app = muffin.Application(SENTRY_DSN="http://public:secret@example.com/1")
    version = metadata.version("muffin-sentry")

    sentry = muffin_sentry.Plugin(
        app, sdk_options={"environment": "tests", "release": version},
    )
    assert sentry.app

    return app


async def test_muffin_sentry(app, client):
    import sentry_sdk

    sentry = app.plugins["sentry"]
    assert sentry

    hub = sentry_sdk.Hub.current
    assert hub.client.options["release"]
    assert hub.client.options["environment"] == "tests"

    @app.route("/success")
    async def success(request):
        return "OK"

    res = await client.get("/success")
    assert res.status_code == 200

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
        if hasattr(request, "user"):
            event["user"] = request.user
        return event

    await app.lifespan.run("startup")

    with mock.patch("sentry_sdk.transport.HttpTransport.capture_event") as mocked:
        res = await client.get("/error")
        assert res.status_code == 500
        assert mocked.called
        (event,), _ = mocked.call_args
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
        (event,), _ = mocked.call_args
        assert event["request"]
        assert event["tags"]
        assert event["user"]

        mocked.reset_mock()

        res = await client.get("/success?md_error=1")
        assert res.status_code == 500
        assert mocked.called
        (event,), _ = mocked.call_args
        assert event["exception"]["values"][0]["mechanism"] is None


# ruff: noqa: TRY002, ARG001
