from __future__ import absolute_import
import os.path

from sio.compilers.common import Compiler
from sio.workers.util import tempcwd


class FPCCompiler(Compiler):
    lang = 'pas'
    output_file = 'a'

    def _make_cmdline(self, executor):
        # Additional sources are automatically included
        return ['fpc', 'a.pas'] + self.options + list(self.extra_compilation_args)

    def _run_in_executor(self, executor):
        # Generate FPC configuration
        with open(os.path.join(executor.path, 'fpc.cfg.in')) as f:
            fpc_cfg = f.read()
        fpc_cfg = fpc_cfg.replace('__DIR__', executor.rpath.rstrip(os.sep))
        with open(tempcwd('fpc.cfg'), 'w') as f:
            f.write(fpc_cfg)

        return super(FPCCompiler, self)._run_in_executor(executor)

    @classmethod
    def fpc2_6_2(cls):
        obj = cls('fpc.2_6_2')
        obj.options = ['-O2', '-XS', '-Xt']
        return obj


def run_fpc_default(environ):
    return FPCCompiler.fpc2_6_2().compile(environ)


def run_fpc2_6_2(environ):
    return FPCCompiler.fpc2_6_2().compile(environ)


run_pas_default = run_fpc_default
run_pas_fpc2_6_2 = run_fpc2_6_2
