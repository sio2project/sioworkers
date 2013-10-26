import os.path
from sio.compilers import common

COMPILER_OPTIONS = ['-static', '-O2', '-s', '-lm']

def run(environ, lang, extra_options=[]):
    if lang == 'c':
        compiler_exe = 'gcc'
        extension = 'c'
    elif lang == 'cpp':
        compiler_exe = 'g++'
        extension = 'cpp'
    else:
        raise ValueError("Unexpected language name: " + lang)

    def include_callback(executor, cmd):
        return cmd + ['-I', os.path.join(executor.rpath, 'usr', 'include')]

    return common.run(environ=environ,
               lang=lang,
               compiler=compiler_exe,
               extension=extension,
               output_file='a.out',
               compiler_options=(COMPILER_OPTIONS + extra_options),
               sandbox=True,
               sandbox_callback=include_callback)

def run_gcc(environ):
    return run(environ, 'c')

def run_gplusplus(environ):
    return run(environ, 'cpp')

def run_default(environ, lang):
    environ['compiler'] = 'gcc.4_6_3'
    extra_options = []
    if lang == 'cpp':
        extra_options = ['-std=gnu++0x']
    return run(environ, lang, extra_options)

def run_default_c(environ):
    return run_default(environ, 'c')

def run_default_cpp(environ):
    return run_default(environ, 'cpp')

