from sio.compilers import common

def run(environ):
    return common.run(environ=environ,
               lang='pas',
               compiler='fpc',
               extension='pas',
               output_file='a',
               compile_additional_sources=False)

