import contextlib
import os, os.path
from sio.workers import ft
from sio.workers.sandbox import get_sandbox, NullSandbox
from sio.workers.execute import execute, noquote

def run(environ, no_sandbox=False):
    ft.download(environ, 'out_file', 'out', skip_if_exists=True)
    ft.download(environ, 'hint_file', 'hint', add_to_cache=True)
    if environ.get('chk_file'):
        sandbox = NullSandbox()
        ft.download(environ, 'in_file', 'in', skip_if_exists=True,
                add_to_cache=True)
        ft.download(environ, 'chk_file', 'chk', add_to_cache=True)
        os.chmod('chk', 0700)
        cmd = ['./chk', 'in', 'out', 'hint', noquote('2>'), '/dev/null']
    elif no_sandbox:
        sandbox = NullSandbox()
        cmd = ['diff', '-b', '-q', 'out', 'hint', noquote('>'), '/dev/null',
                noquote('2>&1'), noquote('&&'), 'echo', 'OK']
    else:
        sandbox = get_sandbox('exec-sandbox')
        cmd = [os.path.join(sandbox.path, 'bin', 'compare'), 'hint', 'out',
                noquote('2>'), '/dev/null']

    with sandbox:
        retcode, output = execute(cmd, ignore_errors=True, split_lines=True)

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
