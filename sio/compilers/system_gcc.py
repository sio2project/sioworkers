from __future__ import absolute_import
import os.path

from sio.compilers.common import Compiler
from sio.workers.util import tempcwd


class CStyleCompiler(Compiler):
    lang = 'c'
    output_file = 'a.out'
    # CStyleCompiler customization
    compiler = 'gcc'  # Compiler to use
    options = []  # Compiler options

    def _make_cmdline(self, executor):
        cmdline = [self.compiler, tempcwd(self.source_file),
                    '-o', tempcwd(self.output_file)] + \
                    self.options + list(self.extra_compilation_args)

        cmdline.extend(tempcwd(os.path.basename(source))
            for source in self.additional_sources)
        return cmdline


class CCompiler(CStyleCompiler):
    compiler = 'gcc'
    # Without -static as there is no static compilation on Mac
    options = ['-O2', '-s', '-lm']


class CPPCompiler(CStyleCompiler):
    lang = 'cpp'
    compiler = 'g++'
    options = ['-std=gnu++0x', '-O2', '-s', '-lm']


def run_gcc(environ):
    return CCompiler().compile(environ)


def run_gplusplus(environ):
    return CPPCompiler().compile(environ)
