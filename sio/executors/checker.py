import os.path
from sio.workers import ft
from sio.workers.executors import UnprotectedExecutor, noquote, SandboxExecutor

def _run_diff():
    with UnprotectedExecutor() as e:
        renv = e(['diff', '-b', '-q', 'out', 'hint'], extra_ignore_errors=(1,))
    return renv['return_code'] and 'WA' or 'OK'

def run(environ, no_sandbox=False):
    ft.download(environ, 'out_file', 'out', skip_if_exists=True)
    ft.download(environ, 'hint_file', 'hint', add_to_cache=True)

    if environ.get('chk_file'):
        ft.download(environ, 'in_file', 'in', skip_if_exists=True,
                add_to_cache=True)
        ft.download(environ, 'chk_file', 'chk', add_to_cache=True)
        os.chmod('chk', 0700)

        with UnprotectedExecutor() as e:
            renv = e(['./chk', 'in', 'out', 'hint'], capture_output=True,
                     ignore_errors=True, split_lines=True)
        output = renv['stdout']
    elif no_sandbox:
        output = [_run_diff()]
    else:
        with SandboxExecutor('exec-sandbox') as e:
            renv = e([os.path.join('bin', 'compare'), 'hint', 'out'],
                  capture_output=True, split_lines=True, ignore_errors=True)
        output = renv['stdout']

    while len(output) < 3:
        output.append('')
    if output[0] == 'OK':
        environ['result_code'] = 'OK'
        if output[1]:
            environ['result_string'] = output[1]
        environ['result_percentage'] = float(output[2] or 100)
    else:
        environ['result_code'] = 'WA'
        environ['result_string'] = output[1]
        environ['result_percentage'] = 0
    return environ
