Muffin-Sentry
#############

.. _description:

**Muffin-Sentry** — Sentry_ integration for the Muffin_ ASGI framework.

.. _badges:

.. image:: https://github.com/klen/muffin-sentry/workflows/tests/badge.svg
    :target: https://github.com/klen/muffin-sentry/actions
    :alt: Tests Status

.. image:: https://img.shields.io/pypi/v/muffin-sentry
    :target: https://pypi.org/project/muffin-sentry/
    :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/muffin-sentry
    :target: https://pypi.org/project/muffin-sentry/
    :alt: Python Versions

.. image:: https://img.shields.io/github/license/klen/muffin-sentry
    :target: https://opensource.org/licenses/MIT
    :alt: License

.. _contents:

.. contents::

Requirements
============

- Python >= 3.10
- Muffin >= 1.0
- sentry-sdk >= 1.40

Installation
============

Install using pip:

.. code-block:: bash

    pip install muffin-sentry

Usage
=====

.. code-block:: python

    from muffin import Application
    import muffin_sentry

    app = Application("example", SENTRY_DSN="https://<public>@sentry.io/<project_id>")

    # Initialize the plugin manually (optional if config is provided)
    sentry = muffin_sentry.Plugin()
    sentry.setup(app)

    # Add custom processor (must be sync)
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

Configuration Options
=====================

You can configure the plugin in two ways:

1. **Via Muffin application config (recommended)**:

.. code-block:: python

    app = Application(
        "app",
        SENTRY_DSN="https://...",
        SENTRY_SDK_OPTIONS={"traces_sample_rate": 0.5},
    )

2. **Or by calling `.setup()` manually**:

.. code-block:: python

    sentry.setup(app, dsn="https://...", sdk_options={"traces_sample_rate": 0.5})

Available options:

=========================== ======================================= ===========================
Name                        Default value                           Description
--------------------------- --------------------------------------- ---------------------------
**dsn**                     ``""``                                  Sentry DSN for your project
**sdk_options**             ``{}``                                  Dict of options for sentry-sdk (e.g., traces_sample_rate)
**ignore_errors**           ``[ResponseError, ResponseRedirect]``   Exception classes to ignore
=========================== ======================================= ===========================

Notes
=====

- You can access the current Sentry scope using `plugin.scope`.
- Event processors must be **synchronous** functions.
- Sentry sessions and transactions are handled automatically inside the plugin middleware.

Bug Tracker
===========

Found a bug or have a feature request?
Please open an issue at: https://github.com/klen/muffin-sentry/issues

Contributing
============

Development happens at: https://github.com/klen/muffin-sentry

Pull requests and suggestions are welcome!

License
=======

Licensed under the `MIT license`_.

Credits
=======

- Created by `klen`_ (Kirill Klenov)

.. _links:

.. _Sentry: https://sentry.io/
.. _Muffin: https://github.com/klen/muffin
.. _MIT license: https://opensource.org/licenses/MIT
.. _klen: https://github.com/klen
