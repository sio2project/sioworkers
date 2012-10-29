import os.path
from sio.workers import ft, Failure
from sio.workers.execute import execute, noquote
from sio.workers.sandbox import get_sandbox

from sio.executors import checker

_supervisor_codes = {
        0: 'OK',
        120: 'OLE',
        121: 'RV',
        124: 'MLE',
        125: 'TLE'
    }

def _supervisor_result_to_code(result):
    return _supervisor_codes.get(int(result), 'RE')

_options = [
        ('MEM_LIMIT', 66000),
        ('TIME_LIMIT', 30000),
        ('OUT_LIMIT', 50000000),
        ('ET_LIMIT', 0),
    ]

def run(environ):
    exe_file = ft.download(environ, 'exe_file', 'exe', add_to_cache=True)
    os.chmod(exe_file, 0700)
    in_file = ft.download(environ, 'in_file', 'in', add_to_cache=True)
    env = os.environ.copy()
    for key, default in _options:
        value = environ.get('exec_' + key.lower(), default)
        env[key] = value

    with get_sandbox('exec-sandbox') as sandbox:
        retcode, output = execute(
                [os.path.join(sandbox.path, 'bin', 'supervisor'), '-f', '3',
                    './exe',
                    noquote('<'), 'in', noquote('3>'), 'supervisor_result',
                    noquote('>'), 'out'], env=env)

    result_file = open('supervisor_result')
    status_line = result_file.readline().strip().split()
    environ['result_string'] = result_file.readline().strip()
    result_file.close()

    for num, key in enumerate((None, 'result_code', 'time_used',
            'exectime_used', 'mem_used', 'num_syscalls')):
        if key:
            environ[key] = int(status_line[num])
    result_code = _supervisor_result_to_code(environ['result_code'])
    environ['result_code'] = result_code

    if result_code == 'OK' and environ.get('check_output'):
        environ = checker.run(environ)

    if 'out_file' in environ:
        ft.upload(environ, 'out_file', 'out',
            to_remote_store=environ.get('upload_out', False))

    return environ
