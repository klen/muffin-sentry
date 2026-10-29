# Muffin-Sentry

**Muffin-Sentry** — [Sentry](https://sentry.io/) integration for the [Muffin](https://github.com/klen/muffin) ASGI framework.

![Tests Status](https://github.com/klen/muffin-sentry/workflows/tests/badge.svg)
[![PyPI Version](https://img.shields.io/pypi/v/muffin-sentry)](https://pypi.org/project/muffin-sentry/)
[![Python Versions](https://img.shields.io/pypi/pyversions/muffin-sentry)](https://pypi.org/project/muffin-sentry/)
[![License](https://img.shields.io/github/license/klen/muffin-sentry)](https://opensource.org/licenses/MIT)

---

## Requirements

- Python 3.11 - 3.15
- Muffin
- sentry-sdk >= 2, < 3

## Installation

Install using pip:

```bash
pip install muffin-sentry
```

## Usage

```python
from muffin import Application
import muffin_sentry

app = Application("example", SENTRY_DSN="https://<public>@sentry.io/<project_id>")
sentry = muffin_sentry.Plugin(app)

# Add a custom processor (must be sync)
@sentry.processor
def enrich_event(event, hint, request):
    if user := getattr(request, "user", None):
        event["user"] = {"id": str(user.id)}
    return event

# Raise unhandled exception
@app.route("/fail")
async def fail(request):
    raise RuntimeError("Boom")

# Manually capture a message
@app.route("/capture")
async def capture(request):
    sentry.capture_message("Manual log")
    return "OK"

# Update scope manually
@app.route("/scope")
async def tag_scope(request):
    sentry.scope.set_tag("section", "test")
    sentry.capture_exception(Exception("With scope tag"))
    return "OK"
```

`Plugin(app)` calls `setup()` for you. Calling `muffin_sentry.Plugin()` and then `sentry.setup(app)` is
equivalent.

## Configuration

Options are read from the application config with the `SENTRY_` prefix (`SENTRY_DSN`,
`SENTRY_SDK_OPTIONS`, ...), or from environment variables with the `{CFG.NAME}_SENTRY_` prefix,
`MUFFIN_SENTRY_` by default. JSON is parsed for complex values:

```bash
export MUFFIN_SENTRY_DSN=https://<public>@sentry.io/<project_id>
export MUFFIN_SENTRY_SDK_OPTIONS='{"environment": "production", "traces_sample_rate": 0.05}'
```

Environment variables are applied by Muffin before the plugin is set up, so they win over the values
passed to `Application(...)`.

1. **Via Muffin application config (recommended)**:

```python
app = Application(
    "app",
    SENTRY_DSN="https://...",
    SENTRY_SDK_OPTIONS={"traces_sample_rate": 0.5},
)
```

2. **Or by calling `.setup()` manually**:

```python
sentry.setup(app, dsn="https://...", sdk_options={"traces_sample_rate": 0.5})
```

Available options:

| Name            | Default value                                              | Description                                                |
| --------------- | ---------------------------------------------------------- | ---------------------------------------------------------- |
| `dsn`           | `""`                                                       | Sentry DSN; when empty `sentry_sdk.init()` is never called |
| `sdk_options`   | `{"traces_sample_rate": 0.1, "profiles_sample_rate": 0.0}` | Keyword arguments for `sentry_sdk.init()`                  |
| `ignore_errors` | `(ResponseError, ResponseRedirect)`                        | Exception classes the middleware reports no event for      |

`sdk_options` is replaced as a whole (no deep merge), so a custom dict has to repeat the defaults you
want to keep:

```python
app = Application(
    "app",
    SENTRY_DSN="https://...",
    SENTRY_SDK_OPTIONS={
        "environment": "production",
        "release": "myapp@1.4.2",
        "traces_sample_rate": 0.05,  # 10% default, 0 disables tracing
        "send_default_pii": True,  # send user IPs and headers to Sentry
    },
)
```

The two defaults are Muffin's "the request was answered" exceptions, not failures: `ResponseError`
(`raise ResponseError(404)`, also what Muffin answers for an unknown route) and `ResponseRedirect`
(`raise ResponseRedirect(...)`, used by `muffin.redirect`). Both derive from `BaseException` in
asgi-tools, so they already slip past the middleware's `except Exception`; the option is there for your
own classes, and it compares by exact type, so a subclass of either class is still reported.

## API

### `plugin.scope`

Property returning the current Sentry `Scope` (`sentry_sdk.get_current_scope()`). Inside a request it is
the isolation scope created by the middleware, so tags, users and breadcrumbs set there are attached to
events captured during that request. Before `setup()` it returns the global scope; it never raises.

### `plugin.processor(fn)`

Decorator registering an event processor. `fn(event, hint, request)` is called synchronously from
`process_data()` after the request context (`url`, `query_string`, `method`, `headers`, `REMOTE_ADDR`)
has been added to the event. Return the modified event, or `None` to keep the event unchanged. Processors
are never awaited: an `async def` processor returns a coroutine that is stored as the event, so keep
them synchronous.

### `plugin.capture_exception(exc)` / `plugin.capture_message(msg)`

Proxies to `sentry_sdk.capture_exception()` / `capture_message()` that do nothing when `dsn` is empty.
The difference from calling the SDK directly is what is attached: the request isolation scope, the
plugin's tags (`framework`, `asgi.type`), the scope modified by your processors and the active
transaction all come along automatically.

### `plugin.middleware`

Runs around every request:

- opens an isolation scope, clears breadcrumbs, tags `framework=muffin` and `asgi.type`
  (`http`/`websocket`/...), and registers the event processor that fills `event["request"]`;
- calls `sentry_sdk.start_session()`;
- continues the incoming trace (`sentry-trace`/`baggage` headers) and starts a transaction named after
  the request path with `op="{asgi.type}.server"`, so distributed traces connect the frontend request
  with backend errors;
- sets the HTTP status on the transaction and captures unhandled exceptions, except the classes listed
  in `ignore_errors`.

Consequently a request that ends up with `ResponseError` (Muffin's 404, for example) produces a
transaction but no error event. Disable tracing by setting `traces_sample_rate` to `0` in `sdk_options`.

## Notes

- Event processors must be **synchronous** functions.
- Sentry sessions and transactions are handled automatically inside the plugin middleware.
- `sentry_sdk.init()` is called only when `dsn` is set; without it the plugin is a thin no-op.

## Bug Tracker

Found a bug or have a feature request?
Please open an issue at: https://github.com/klen/muffin-sentry/issues

## Contributing

Development happens at: https://github.com/klen/muffin-sentry

Pull requests and suggestions are welcome!

## License

Licensed under the [MIT license](https://opensource.org/licenses/MIT).

## Credits

- Created by [klen](https://github.com/klen) (Kirill Klenov)
