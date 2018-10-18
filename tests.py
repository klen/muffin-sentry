import mock
import muffin
import pytest


@pytest.fixture(scope='session')
def app():
    app_ = muffin.Application(
        'sentry', PLUGINS=['muffin_sentry'], SENTRY_DSN="http://public:secret@example.com/1"
    )

    @app_.register('/success')
    def success(request):
        return 'OK'

    @app_.register('/error')
    def error(request):
        raise Exception('Unhandled exception')

    return app_


async def test_muffin_sentry(app, client):
    assert app.ps.sentry

    resp = await client.get('/success')
    assert resp.status == 200

    with mock.patch.object(app.ps.sentry.client, 'send') as mocked:
        resp = await client.get('/error')
        assert resp.status == 500

    assert mocked.called
    assert mocked.call_args[1]['request']
