from sio.compilers import common

COMPILER_OPTIONS = ('-O2', '-s')

def run(environ, lang):
    if lang == 'c':
        compiler_exe = 'gcc'
        extension = 'c'
    elif lang == 'cpp':
        compiler_exe = 'g++'
        extension = 'cpp'
    else:
        raise ValueError("Unexpected language name: " + lang)

    return common.run(environ=environ,
               lang=lang,
               compiler=compiler_exe,
               extension=extension,
               output_file='a.out',
               compiler_options=COMPILER_OPTIONS)

def run_gcc(environ):
    return run(environ, 'c')

def run_gplusplus(environ):
    return run(environ, 'cpp')

