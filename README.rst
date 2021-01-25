Muffin-Sentry
#############

.. _description:

**Muffin-Sentry** -- Sentry_ Integration for Muffin_ framework

.. _badges:

.. image:: https://github.com/klen/muffin-sentry/workflows/tests/badge.svg
    :target: https://github.com/klen/muffin-sentry/actions
    :alt: Tests Status

.. image:: https://img.shields.io/pypi/v/muffin-sentry
    :target: https://pypi.org/project/muffin-sentry/
    :alt: PYPI Version

.. _contents:

.. contents::

.. _requirements:

Requirements
=============

- python >= 3.8

.. _installation:

Installation
=============

**Muffin-Sentry** should be installed using pip: ::

    pip install muffin-sentry

.. _usage:

Usage
=====

.. code-block:: python

    from muffin import Application
    import muffin_sentry

    # Create Muffin Application
    app = Application('example')

    # Initialize the plugin
    # As alternative: jinja2 = Jinja2(app, **options)
    sentry = muffin_sentry.Plugin()
    sentry.setup(app, dsn="DSN_URL")

    # Use it inside your handlers

    # The exception will be send to Sentry
    @app.route('/unhandled')
    async def catch_exception(request):
        raise Exception('unhandled')

    # Capture a message by manual
    @app.route('/capture_message')
    async def message(request):
        sentry.capture_message('a message from app')
        return 'OK'

    # Capture an exception by manual
    @app.route('/capture_exception')
    async def exception(request):
        sentry.capture_exception(Exception())
        return 'OK'

    # Update Sentry Scope
    @app.route('/update_user')
    async def user(request):
        scope = sentry.current_scope.get()
        scope.set_user({'id': 1, 'email': 'example@example.com'})
        sentry.capture_exception(Exception())
        return 'OK'


Options
-------

Format: ``Name`` -- Description (``default value``)

``dsn``  -- Sentry DSN for your application (``''``)

``sdk_options`` -- Additional options for Sentry SDK Client (``{}``). See https://docs.sentry.io/platforms/python/configuration/options/

``ignore_errors`` -- Exception Types to Ignore (``[muffin.ResponseRedirect, muffin.ResponseError]``) 

You are able to provide the options when you are initiliazing the plugin:

.. code-block:: python

    sentry.setup(app, dsn='DSN_URL')


Or setup it inside ``Muffin.Application`` config using the ``SENTRY_`` prefix:

.. code-block:: python

   SENTRY_DSN = 'DSN_URL'

`Muffin.Application` configuration options are case insensetive

.. _bugtracker:

Bug tracker
===========

If you have any suggestions, bug reports or
annoyances please report them to the issue tracker
at https://github.com/klen/muffin-sentry/issues

.. _contributing:

Contributing
============

Development of Muffin-Sentry happens at: https://github.com/klen/muffin-sentry


Contributors
=============

* klen_ (Kirill Klenov)

.. _license:

License
========

Licensed under a `MIT license`_.

.. _links:


.. _klen: https://github.com/klen
.. _Muffin: https://github.com/klen/muffin
.. _Sentry: https://sentry.io/

.. _MIT license: http://opensource.org/licenses/MIT
