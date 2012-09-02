import os.path

from sio.compilers import common

def run(environ):
    def sandbox_callback(sandbox):
        fpc_cfg = open(os.path.join(sandbox.path, 'fpc.cfg.in')).read()
        fpc_cfg = fpc_cfg.replace('__DIR__', os.path.abspath(sandbox.path))
        open('fpc.cfg', 'w').write(fpc_cfg)

    return common.run(environ=environ,
               lang='pas',
               compiler='fpc',
               extension='pas',
               output_file='a',
               compile_additional_sources=False,
               sandbox=True,
               sandbox_callback=sandbox_callback)

def run_default(environ):
    environ['compiler'] = 'fpc.2_4_2'
    return run(environ)
