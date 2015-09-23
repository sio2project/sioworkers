import os.path

from sio.compilers.common import Compiler


class FPCCompiler(Compiler):
    sandbox = 'fpc.2_6_2'
    lang = 'pas'
    options = ['-O2', '-XS', '-Xt']
    output_file = 'a'

    def _make_cmdline(self, executor):
        # Additional sources are automatically included
        return ['fpc', 'a.pas'] + self.options + \
                list(self.extra_compilation_args)

    def _run_in_executor(self, executor):
        # Generate FPC configuration
        with open(os.path.join(executor.path, 'fpc.cfg.in')) as f:
            fpc_cfg = f.read()
        fpc_cfg = fpc_cfg.replace('__DIR__', executor.rpath.rstrip(os.sep))
        with open('fpc.cfg', 'w') as f:
            f.write(fpc_cfg)

        return super(FPCCompiler, self)._run_in_executor(executor)


def run(environ):
    return FPCCompiler().compile(environ)


run_default = run
