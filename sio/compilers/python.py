# pylint: disable=attribute-defined-outside-init
from __future__ import absolute_import
import os.path
import glob
import logging
import shutil
import tarfile

from sio.compilers.common import Compiler
from sio.workers.util import tempcwd

logger = logging.getLogger(__name__)

class PythonCompiler(Compiler):
    lang = 'py'
    output_file = 'a.tar'
    python_executable_path = None

    def _make_filename(self):
        source_base = os.path.basename(self.environ['source_file'])
        self.module_name = self.environ.get('problem_short_name',
                                            os.path.splitext(source_base)[0])
        return 'a/%s.py' % self.module_name

    def _run_in_executor(self, executor):
        python = [self.python_executable_path]

        source_dir = os.path.dirname(self.source_file)

        compileall = python + ['-m', 'compileall',
                               self.rcwd(source_dir),
                              ]
        renv = self._execute(executor, compileall)
        if renv['return_code']:
            return renv

        with tarfile.open(tempcwd(self.output_file), 'w:') as tar:
            tar.add(tempcwd(source_dir), '.', True)

        return renv

    def _execute(self, executor, cmdline, **kwargs):
        kwargs.setdefault('mem_limit', None)
        kwargs.setdefault('binds', []).extend([
                    ('/dev/zero', '/dev/urandom', 'ro,dev'),
                ])
        return super(PythonCompiler, self)._execute(executor, cmdline, **kwargs)

    def _postprocess(self, renv):
        environ = super(PythonCompiler, self)._postprocess(renv)
        if environ['result_code'] == 'OK':
            environ['exec_info'] = {
                    'mode': 'python3',
                    'version': self.sandbox,
                    'python_bin': self.python_executable_path,
                    'preferred_filename': 'a.tar',
                    'main_file': '%s.py' % self.module_name,
            }
        return environ

    @classmethod
    def get_instance(cls, version):
        obj = cls('python' + version)
        version_parts = version.replace('-', '.').replace('_', '.').split('.')
        short_version = '.'.join(version_parts[:2])
        obj.python_executable_path = '/usr/bin/python' + short_version
        return obj


def run_python(environ, version):
    return PythonCompiler().get_instance(version).compile(environ)


run_python3_9_numpy_amd64 = lambda environ: run_python(environ, '3.9.2-numpy_amd64')
run_python3_11_numpy_amd64 = lambda environ: run_python(environ, '3.11.2-numpy_amd64')
run_python3_13_numpy_amd64 = lambda environ: run_python(environ, '3.13.5-numpy')
run_python_default = run_python3_13_numpy_amd64
