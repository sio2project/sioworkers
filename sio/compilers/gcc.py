import os.path
from sio.compilers import common
from sio.workers.sandbox import get_sandbox

COMPILER_OPTIONS = ['-static', '-O2', '-s']

def run(environ, lang):
    if lang == 'c':
        compiler_exe = 'gcc'
        extension = 'c'
    elif lang == 'cpp':
        compiler_exe = 'g++'
        extension = 'cpp'
    else:
        raise ValueError("Unexpected language name: " + lang)

    sandbox = get_sandbox('compiler-' + environ['compiler'])
    compiler_options = \
        ['-I', os.path.join(sandbox.path, 'usr', 'include')] \
        + COMPILER_OPTIONS

    return common.run(environ=environ,
               lang=lang,
               compiler=compiler_exe,
               extension=extension,
               output_file='a.out',
               compiler_options=compiler_options,
               sandbox=sandbox)

def run_gcc(environ):
    return run(environ, 'c')

def run_gplusplus(environ):
    return run(environ, 'cpp')

def run_default(environ, lang):
    environ['compiler'] = 'gcc.sio20120206'
    return run(environ, lang)

def run_default_c(environ):
    return run_default(environ, 'c')

def run_default_cpp(environ):
    return run_default(environ, 'cpp')

