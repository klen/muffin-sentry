from unittest import mock

import muffin
import pytest


@pytest.fixture
def app():
    import muffin_sentry

    app = muffin.Application(SENTRY_DSN="http://public:secret@example.com/1")

    sentry = muffin_sentry.Plugin(app)
    assert sentry.app

    return app


async def test_muffin_sentry(app, client):
    sentry = app.plugins['sentry']
    assert sentry

    @app.route('/success')
    async def success(request):
        return 'OK'

    res = await client.get('/success')
    assert res.status_code == 200

    @app.route('/error')
    async def error(request):
        raise Exception('Unhandled exception')

    with mock.patch('sentry_sdk.transport.HttpTransport.capture_event') as mocked:
        res = await client.get('/error')
        assert res.status_code == 500
        assert mocked.called
        (event,), _ = mocked.call_args
        assert event['request']
        assert event['request']['url'] == 'http://localhost/error'

        @app.route('/scope')
        async def scope(request):
            scope = sentry.current_scope.get()
            scope.set_tag('tests', 'passed')
            scope.set_user({'id': '1', 'email': 'test@test.com'})
            app.plugins['sentry'].captureMessage('tests')
            return 'OK'

        res = await client.get('/scope')
        assert res.status_code == 200
        assert mocked.called
        (event,), _ = mocked.call_args
        assert event['request']
        assert event['tags']
        assert event['user']
