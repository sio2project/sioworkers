from __future__ import absolute_import
from __future__ import print_function
import os
import sys
import traceback
import logging
import platform
import six
import json

from sio.workers import Failure
from sio.workers.util import first_entry_point, TemporaryCwd, json_dumps
from sio.workers.ft import init_instance


logger = logging.getLogger(__name__)


def _run_filters(key, environ):
    for f in environ.get(key, ()):
        environ = first_entry_point('sio.workers.filters', f)(environ)
    return environ


def _add_meta(environ):
    environ['worker'] = platform.node()
    return environ


def _save_failure(exc, environ):
    environ['result'] = 'FAILURE'
    environ['exception'] = str(exc)
    environ['traceback'] = traceback.format_exc()
    return environ


def _print_environ(environ):
    print('--- BEGIN ENVIRON ---')
    print(json_dumps(environ))
    print('--- END ENVIRON ---')


def run(environ):
    """Performs the work passed in ``environ``.

    Returns the modified ``environ``. It might be modified in-place by work
    implementations.

    The following keys in ``environ`` have special meaning:

    ``job_type``
      Mandatory key naming the job to be run.

    ``prefilters``
      Optional list of filter names to apply before performing the work.

    ``postfilters``
      Optional list of filter names to apply after performing the work.

    The following are added during processing:

    ``worker``
      Hostname of the machine running the job (i.e. the machine executing
      this function).

    Refer to :ref:`sio-workers-filters` for more information about filters.
    """

    with TemporaryCwd():
        try:
            if environ.get('filetracker_url', None):
                init_instance(environ['filetracker_url'])
            environ = _run_filters('prefilters', environ)
            environ = _add_meta(environ)
            environ = first_entry_point('sio.jobs', environ['job_type'])(environ)
            environ['result'] = 'SUCCESS'
            environ = _run_filters('postfilters', environ)
        except Failure as e:
            environ = _save_failure(e, environ)
            try:
                environ = _run_filters('postfilters', environ)
            except Failure as e:
                pass

    return environ


def main():
    environ = json.loads(os.environ['environ'])
    if isinstance(environ, six.string_types):
        # Hudson quotes one more time if using the web interface.
        environ = json.loads(environ)
    if not isinstance(environ, dict):
        raise ValueError("Environment deserialized not to dict: %r" % environ)

    if len(sys.argv) > 2:
        raise ValueError(
            "Unexpected command-line arguments: %s", ', '.join(sys.argv[1:])
        )
    if len(sys.argv) == 2:
        environ['job_type'] = sys.argv[1]

    level = logging.INFO
    if environ.get('debug'):
        level = logging.DEBUG
    logging.basicConfig(
        format="%(asctime)-15s %(name)s %(levelname)s: %(message)s", level=level
    )

    logger.info('starting job')

    for key in ('prefilters', 'postfilters'):
        if key in os.environ:
            environ[key] = environ.get(key, []) + os.environ[key].split()
    environ = run(environ)

    logger.info('finished job')

    _print_environ(environ)


if __name__ == '__main__':
    main()
