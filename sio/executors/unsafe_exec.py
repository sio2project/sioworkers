import os.path
import re
from sio.workers import ft, Failure
from sio.workers.execute import execute, noquote

from sio.executors import checker

TIME_OUTPUT_RE = re.compile(r'^user\s+([0-9]+)m([0-9.]+)s$', re.MULTILINE)

def run(environ):
    exe_file = ft.download(environ, 'exe_file', 'exe', add_to_cache=True)
    os.chmod(exe_file, 0700)
    in_file = ft.download(environ, 'in_file', 'in', add_to_cache=True)

    if 'exec_time_limit' in environ:
        time_limit = environ['exec_time_limit']
        time_ulimit = (time_limit + 999) / 1000
    else:
        time_limit = time_ulimit = None
    if 'exec_mem_limit' in environ:
        mem_limit = environ['exec_mem_limit'] / 1024
    else:
        mem_limit = None

    retcode, output = execute(['bash', '-c', 'time ./exe < in > out'],
        time_limit=time_ulimit, mem_limit=mem_limit, ignore_errors=True)

    time_output_matches = TIME_OUTPUT_RE.findall(output)
    if time_output_matches:
        mins, secs = time_output_matches[-1]
        time_used = int((int(mins) * 60 + float(secs)) * 1000)
    else:
        raise RuntimeError('Could not find output of time program. '
            'Captured output: %s' % output)

    if time_limit is not None and time_used >= 0.99 * time_limit:
        environ['result_string'] = 'time limit exceeded'
        environ['result_code'] = 'TLE'
    elif retcode == 0:
        environ['result_string'] = 'ok'
        environ['result_code'] = 'OK'
    else:
        environ['result_string'] = 'program exited with code %d' % retcode
        environ['result_code'] = 'RE'
    environ['time_used'] = time_used
    environ['exectime_used'] = 0
    environ['mem_used'] = 0
    environ['num_syscalls'] = 0

    if environ['result_code'] == 'OK' and environ.get('check_output'):
        environ = checker.run(environ, no_sandbox=True)

    if 'out_file' in environ:
        ft.upload(environ, 'out_file', 'out',
            to_remote_store=environ.get('upload_out', False))

    return environ
