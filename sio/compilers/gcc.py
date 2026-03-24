from __future__ import absolute_import
from sio.compilers.system_gcc import CStyleCompiler


class CCompiler(CStyleCompiler):
    lang = 'c'

    @classmethod
    def get_instance(cls, sandbox, standard):
        obj = cls(sandbox)
        obj.options = ['-std=' + standard, '-static', '-O3', '-s', '-lm']
        return obj


class CPPCompiler(CStyleCompiler):
    lang = 'cpp'

    @classmethod
    def get_instance(cls, sandbox, standard):
        obj = cls(sandbox)
        obj.compiler = 'g++'
        obj.options = ['-std=' + standard, '-static', '-O3', '-s']
        return obj


def run_gcc(gcc_version, standard, environ):
    return CCompiler.get_instance('gcc.' + gcc_version, standard).compile(environ)


def run_gplusplus(gcc_version, cpp_standard_year, environ):
    return CPPCompiler.get_instance(
        'gcc.' + gcc_version,
        'c++' + str(cpp_standard_year),
    ).compile(environ)


run_c_gcc4_8_2_c99 = lambda environ: run_gcc('4_8_2', 'gnu99', environ)
run_c_gcc12_2_0_c17 = lambda environ: run_gcc('12_2_0', 'c17', environ)
run_c_gcc14_2_0_c17 = lambda environ: run_gcc('14_2_0', 'gnu17', environ)
run_c_default = run_c_gcc14_2_0_c17

run_cpp_gcc4_8_2_cpp11 = lambda environ: run_gplusplus('4_8_2', 11, environ)
run_cpp_gcc6_3_cpp14 = lambda environ: run_gplusplus('6_3_0', 14, environ)
run_cpp_gcc8_3_cpp17 = lambda environ: run_gplusplus('8_3_0-i386', 17, environ)
run_cpp_gcc8_3_cpp17_amd64 = lambda environ: run_gplusplus('8_3_0-amd64', 17, environ)
run_cpp_gcc10_2_cpp17_amd64 = lambda environ: run_gplusplus('10_2_1', 17, environ)
run_cpp_gcc12_2_cpp20_amd64 = lambda environ: run_gplusplus('12_2_0', 20, environ)
run_cpp_gcc14_2_cpp23_amd64 = lambda environ: run_gplusplus('14_2_0', 23, environ)
run_cpp_default = run_cpp_gcc14_2_cpp23_amd64
