# pylint: disable=attribute-defined-outside-init
from __future__ import absolute_import
import os.path
import glob

from sio.compilers.common import Compiler
from sio.workers.util import tempcwd


class JavaCompiler(Compiler):
    lang = 'java'
    output_file = 'a.jar'

    def _make_filename(self):
        source_base = os.path.basename(self.environ['source_file'])
        self.class_name = self.environ.get('problem_short_name',
                                           os.path.splitext(source_base)[0])
        self.class_file = '%s.class' % self.class_name
        return '%s.java' % self.class_name

    def _run_in_executor(self, executor):
        javac = ['javac', '-J-Xss32M'] + list(self.extra_compilation_args) \
                + [tempcwd(self.source_file)]
        javac.extend(tempcwd(os.path.basename(source))
            for source in self.additional_sources)

        renv = self._execute(executor, javac)
        if renv['return_code']:
            return renv

        classes = [os.path.basename(x)
                   for x in glob.glob(tempcwd() + '/*.class')]
        jar = ['jar', 'cf', self.output_file] + classes
        renv2 = self._execute(executor, jar)
        renv2['stdout'] = renv['stdout'] + renv2['stdout']
        return renv2

    def _execute(self, executor, cmdline, **kwargs):
        kwargs.setdefault('mem_limit', None)
        return super(JavaCompiler, self)._execute(executor, cmdline, **kwargs)

    def _postprocess(self, renv):
        environ = super(JavaCompiler, self)._postprocess(renv)
        if environ['result_code'] == 'OK':
            environ['exec_info'] = {
                    'mode': 'java',
                    'main_class': self.class_name,
                    'preferred_filename': '%s.jar' % self.class_name,
            }
        return environ


def run(environ):
    return JavaCompiler().compile(environ)

run_default = run
