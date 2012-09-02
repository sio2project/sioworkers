import sys
import os.path
import pkg_resources
import traceback
try:
    import json
    json.dumps
except (ImportError, AttributeError):
    import simplejson as json

from sio.workers.util import first_entry_point
from sio.workers.execute import execute

def run(environ):
    if 'compiler' not in environ:
        _, extension = os.path.splitext(environ['source_file'])
        environ['compiler'] = 'default-' + extension[1:].lower()
    compiler = first_entry_point('sio.compilers',
            environ['compiler'].split('.')[0])
    environ = compiler(environ)
    assert 'compiler_output' in environ, \
        "Mandatory key 'compiler_output' not returned by job."
    assert 'result_code' in environ, \
        "Mandatory key 'result_code' not returned by job."
    return environ

def main():
    # Simulate compile.sh from sio1
    environ = {
            'source_file': sys.argv[1],
            'out_file': sys.argv[2],
        }
    if len(sys.argv) > 3:
        environ['compiler'] = 'default-' + sys.argv[3].lower()
    run(environ)
    print json.dumps(environ)
