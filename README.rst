Muffin-Sentry
#############

.. _description:

Muffin-Sentry -- Integrate Sentry to Muffin framework.

.. _badges:

.. image:: http://img.shields.io/travis/klen/muffin-sentry.svg?style=flat-square
    :target: http://travis-ci.org/klen/muffin-sentry
    :alt: Build Status

.. image:: http://img.shields.io/pypi/v/muffin-sentry.svg?style=flat-square
    :target: https://pypi.python.org/pypi/muffin-sentry

.. image:: http://img.shields.io/pypi/dm/muffin-sentry.svg?style=flat-square
    :target: https://pypi.python.org/pypi/muffin-sentry

.. _contents:

.. contents::

.. _requirements:

Requirements
=============

- python >= 3.3

.. _installation:

Installation
=============

**Muffin-Sentry** should be installed using pip: ::

    pip install muffin-sentry

.. _usage:

Usage
=====

Add **muffin_sentry** to **PLUGINS** in your Muffin Application configuration.

Options
-------

**SENTRY_DSN**  -- Sentry DSN for your application ('')

**SENTRY_TAGS** -- Additional tags (None)

**SENTRY_PROCESSORS** -- Additional processors (None)

**SENTRY_EXCLUDE_PATHS** -- Exclude paths (None)

Manual use
----------

The plugin starts working automaticaly, but you can use it manually:

.. code:: python

    @app.register('/my')
    def my_view(request):
        # ...
        yield from app.ps.sentry.captureMessage('Hello from my view')
        # ...
        yield from app.ps.sentry.captureException(request=request)

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

If you wish to express your appreciation for the project, you are welcome to send
a postcard to: ::

    Kirill Klenov
    pos. Severny 8-3
    MO, Istra, 143500
    Russia

.. _links:


.. _klen: https://github.com/klen

.. _MIT license: http://opensource.org/licenses/MIT
