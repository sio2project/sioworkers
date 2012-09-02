import os
import sys
import traceback
import tempfile
import shutil
import logging

try:
    import json
    json.dumps
except (ImportError, AttributeError):
    import simplejson as json

from sio.workers import Failure
from sio.workers.util import first_entry_point

logger = logging.getLogger(__name__)

def _run_filters(key, environ):
    for f in environ.get(key, ()):
        environ = first_entry_point('sio.workers.filters', f)(environ)
    return environ

def _save_failure(exc, environ):
    environ['result'] = 'FAILURE'
    environ['exception'] = str(exc)
    environ['traceback'] = traceback.format_exc()
    return environ

def _print_environ(environ):
    print '--- BEGIN ENVIRON ---'
    print json.dumps(environ)
    print '--- END ENVIRON ---'

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

       Refer to :ref:`sio-workers-filters` for more information about filters.
    """

    original_cwd = os.getcwd()
    tmpdir = tempfile.mkdtemp()
    try:
        os.chdir(tmpdir)
        environ = _run_filters('prefilters', environ)
        environ = first_entry_point('sio.jobs', environ['job_type'])(environ)
        environ['result'] = 'SUCCESS'
        environ = _run_filters('postfilters', environ)
    except Failure, e:
        environ = _save_failure(e, environ)
        try:
            environ = _run_filters('postfilters', environ)
        except Failure, e:
            pass
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmpdir)

    return environ

def main():
    environ = json.loads(os.environ['environ'])
    if isinstance(environ, basestring):
        # Hudson quotes one more time if using the web interface.
        environ = json.loads(environ)
    if not isinstance(environ, dict):
        raise ValueError("Environment deserialized not to dict: %r" % environ)

    if len(sys.argv) > 2:
        raise ValueError("Unexpected command-line arguments: %s",
                ', '.join(sys.argv[1:]))
    if len(sys.argv) == 2:
        environ['job_type'] = sys.argv[1]

    level = logging.INFO
    if environ.get('debug'):
        level = logging.DEBUG
    logging.basicConfig(
            format="%(asctime)-15s %(name)s %(levelname)s: %(message)s",
            level=level)

    logger.info('starting job')

    for key in ('prefilters', 'postfilters'):
        if key in os.environ:
            environ[key] = environ.get(key, []) + os.environ[key].split()
    environ = run(environ)

    logger.info('finished job')

    _print_environ(environ)

if __name__ == '__main__':
    main()
