# pylint: disable=attribute-defined-outside-init
from __future__ import absolute_import
import os.path
import glob
import six
import logging
import shutil
import tarfile

from sio.compilers.common import Compiler
from sio.workers.util import tempcwd

logger = logging.getLogger(__name__)


class PythonCompiler(Compiler):
    lang = 'py'
    output_file = 'a.tar'
    python = 'python3.7'
    sandbox = '%s-numpy_amd64' % python

    def _make_filename(self):
        source_base = os.path.basename(self.environ['source_file'])
        self.module_name = self.environ.get('problem_short_name',
                                            os.path.splitext(source_base)[0])
        return 'a/%s.py' % self.module_name

    def _process_swig(self, executor, basename):
        swig_in = basename + '.i'
        swig_cxx = basename + '_wrap.cxx'
        swig_o = basename + '_wrap.o'
        lib_cxx = basename + '.cpp'
        lib_o = basename + '.o'
        res_py = basename + '.py'
        res_so = '_%s.so' % basename

        cxxflags = ['-std=c++11', '-O3', '-fPIC']
        includeflag = ['-I/usr/include/%s' % self.python]

        swig = '/usr/bin/swig2.0'
        gxx = '/usr/bin/g++'

        stdout = ''

        swigcmd = [swig, '-c++', '-python', swig_in]
        renv = self._execute(executor, swigcmd)
        stdout += renv['stdout']
        renv['stdout'] = stdout
        if renv['return_code']:
            return renv

        compile_lib = [gxx] + cxxflags + ['-c', lib_cxx]
        renv = self._execute(executor, compile_lib)
        stdout += renv['stdout']
        renv['stdout'] = stdout
        if renv['return_code']:
            return renv

        compile_swig = [gxx] + cxxflags + includeflag + ['-c', swig_cxx]
        renv = self._execute(executor, compile_swig)
        stdout += renv['stdout']
        renv['stdout'] = stdout
        if renv['return_code']:
            return renv

        link = [gxx, '-shared', lib_o, swig_o, '-o', res_so]
        renv = self._execute(executor, link)
        stdout += renv['stdout']
        renv['stdout'] = stdout
        if renv['return_code']:
            return renv

        shutil.move(tempcwd(res_so), tempcwd(self._source_dir))
        shutil.move(tempcwd(res_py), tempcwd(self._source_dir))

        return renv

    def _run_in_executor(self, executor):
        python = ['/usr/bin/%s' % (self.python,)]

        source_dir = os.path.dirname(self.source_file)
        self._source_dir = source_dir

        extra_files = self.environ.get('extra_files', {})
        logger.debug('extra_files: %r', extra_files)
        for extra_file in six.iterkeys(extra_files):
            if not extra_file.endswith('.i'):
                continue

            logger.debug('swig: %s', extra_file)
            renv = self._process_swig(executor, extra_file[:-2])
            if renv['return_code']:
                return renv

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
                    'preferred_filename': 'a.tar',
                    'main_file': '%s.py' % self.module_name,
            }
        return environ


def run(environ):
    return PythonCompiler().compile(environ)


run_default = run
run_py_default = run
run_python_3_7 = run
