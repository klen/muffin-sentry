import mock
import muffin
import pytest
from raven import Client


@pytest.fixture(scope='session')
def app(loop):
    app = muffin.Application(
        'sentry', loop=loop,

        PLUGINS=['muffin_sentry'],
        SENTRY_DSN="http://public:secret@example.com/1"
    )

    @app.register('/success')
    def success(request):
        return 'OK'

    @app.register('/error')
    def error(request):
        raise Exception('Unhandled exception')

    return app


@mock.patch.object(Client, 'send')
def test_muffin_sentry(mocked, app, client):
    assert app.ps.sentry

    response = client.get('/success')
    assert response.text == 'OK'

    with pytest.raises(Exception):
        client.get('/error')
    assert mocked.called
