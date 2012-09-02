SIO Workers
===========

The idea behind ``sioworkers`` module is that sometimes systems need to
perform some relatively long-term computations. This module provides a set
of convenience classes and functions which can be helpful implementing the
batch tasks themselves. It is not a batch-scheduler.

This mission is accomplished by providing a unified pythonic interface for
representing parameters, input and output of batch jobs and running
the jobs once these parameters are available.

The ``environ``
---------------

This mysterious "pythonic interface" is actually a dictionary. Its keys are
strings, and values are Python primitive types, like lists, dictionaries,
strings etc. In practice this may be anything serializable to JSON. This
dictionary is called ``environ`` everywhere. The ``environ`` is the only
argument passed to :func:`sio.workers.runner.run` function and the only thing
returned by it.

Many jobs use the :mod:`filetracker` module, so you may be happier if you
learn about it somewhat.

``environ`` keys common to all jobs
-----------------------------------

Keys that must be present to run a job:

``job_type``
  name of the job to run.

Keys affected by all jobs:

``result``
  ``SUCCESS`` if the job finished without throwing an exception,
  ``FAILURE`` otherwise,

``exception``
  (set only if an exception was thrown) the exception, converted
  to string,

``traceback``
  (set only if an exception was thrown) the traceback, converted
  to string.

Refer to the documentation of a particular job to learn what other
arguments are expected and what information is returned back in
the ``environ``.

In general regular errors which may happen as a result of the job
should not be signalled by throwing an exception (for example
compilation errors for the compilation job). Exceptions should
suggest some potentially important system problems like sandbox
misconfiguration or out of disk space.

Running jobs
------------

From Python:

.. autofunction:: sio.workers.runner.run

There are also bindings for `Celery <http://celeryproject.org/>`_ in
:mod:`sio.celery`.

From the shell, you may use the ``sio-batch`` script, which expects an
environment variable ``environ`` to be some JSON. After running the job, the
output is printed to the standard output in the following format::

    --- BEGIN ENVIRON ---
    <jsonified environ>
    --- END ENVIRON ---


For developers
==============

Hi, developer! Nice to meet you!

Creating jobs
-------------

Creating jobs ist überleicht.

You just need to define a function with one argument... the ``environ``, returning one
thing... the ``environ``. You may define it in any module, provided that
it is registered with ``pkg_resources`` aka ``setuptools`` as an entry point,
under the key ``sio.jobs``.

The function may use the current directory in any way --- it will be run
from inside a temporary directory which will be deleted automatically.

For example, the following ``setup.py`` defines a module with a job named
``szescblotastop``::

  from setuptools import setup, find_packages
  setup(
      name = "mymud",
      version = '0.1',
      packages = find_packages(),
      entry_points = {
          'sio.jobs': [
              'szescblotastop = mudmodule.mudsubmodule.mud.mud.mud:mud_fun',
          ]
      }
  )

Sandboxes
---------

.. autoclass:: sio.workers.sandbox.Sandbox
    :members:

Executing external programs
---------------------------

.. autofunction:: sio.workers.execute.execute

.. _sio-workers-filters:

Interacting with Filetracker
----------------------------

Filetracker should be your friend if you are coding for ``sio-workers``.
We can somewhat help you interacting with it by providing the most
demanded functions in the world:

.. autofunction:: sio.workers.ft.download

.. autofunction:: sio.workers.ft.upload

.. autofunction:: sio.workers.ft.instance

There is also a convenience function for starting the Filetracker
server, but this is only useful in complex setups when one wants to
configure the worker machines to share cached files between themselves.

.. autofunction:: sio.workers.ft.launch_filetracker_server

There is also a command-line script called ``sio-run-filetracker`` which
calls this function.

Example
-------

Here's an example of a job running the specified binary file
in a controlled environment (beware, as this is not the actual
implementation of the ``exec`` job from ``sio-exec`` package)::

  from sio.workers import ft, Failure
  from sio.workers.execute import execute, noquote
  from sio.workers.sandbox import get_sandbox

  def run(environ):
      exe_file = ft.download(environ, 'exe_file', 'exe', add_to_cache=True)
      os.chmod(exe_file, 0700)
      in_file = ft.download(environ, 'in_file', 'in', add_to_cache=True)
      sandbox = get_sandbox('exec-sandbox')
      env = os.environ.copy()
      env['MEM_LIMIT'] = 256000
      retcode, output = execute(
              [os.path.join(sandbox.path, 'bin', 'supervisor'), '-f', '3',
                  './exe',
                  noquote('<'), 'in',
                  noquote('3>'), 'supervisor_result',
                  noquote('>'), 'out'],
              env=env)
      result_file = open('supervisor_result')
      environ['status_line'] = result_file.readline().strip()
      result_file.close()
      ft.upload(environ, 'out_file', 'out')
      return environ

Creating filters
----------------

Filters are boring. There are no filters at the moment.

Filters are functions with one argument... the ``environ``, returning one
thing... the ``environ``. They may be defined in any modules, provided that
they are registered with ``pkg_resources`` aka ``setuptools`` as entry points,
under the key ``sio.workers.filters``.

For example, the following ``setup.py`` defines a module with a filter::

  from setuptools import setup, find_packages
  setup(
      name = "mypackage",
      version = '0.1',
      packages = find_packages(),
      entry_points = {
          'sio.workers.filters': [
              'superfilter = mypackage.submodule:superfilter_function',
          ]
      }
  )

The ``ping`` job
----------------

There is also a single job called ``ping`` available for testing. It expects
an ``ping`` key in the environment and and basically does::

  environ['pong'] = environ['ping']

Integration with Celery
-----------------------

.. automodule:: sio.celery

Available jobs
==============

.. toctree::
   :maxdepth: 1

   compilers
   executors

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
