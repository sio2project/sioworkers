import os.path

from sio.compilers.common import Compiler


class CStyleCompiler(Compiler):
    lang = 'c'
    output_file = 'a.out'
    # CStyleCompiler customization
    compiler = 'gcc'  # Compiler to use
    options = []  # Compiler options

    def _make_cmdline(self, executor):
        cmdline = [self.compiler, self.source_file] + self.options \
                  + list(self.extra_compilation_args)

        cmdline.extend(os.path.basename(source)
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
