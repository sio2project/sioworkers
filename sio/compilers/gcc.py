from sio.compilers.system_gcc import CStyleCompiler


class CCompiler(CStyleCompiler):
    sandbox = 'gcc.4_8_2'
    lang = 'c'
    options = ['-std=gnu99', '-static', '-O2', '-s', '-lm']


class CPPCompiler(CStyleCompiler):
    sandbox = 'gcc.4_8_2'
    lang = 'cpp'
    compiler = 'g++'
    options = ['-std=c++11', '-static', '-O2', '-s', '-lm']


def run_gcc(environ):
    return CCompiler().compile(environ)


def run_gplusplus(environ):
    return CPPCompiler().compile(environ)


run_default_c = run_gcc
run_default_cpp = run_gplusplus
