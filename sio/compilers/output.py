def run(environ):
    environ['result_code'] = 'OK'
    environ['compiler_output'] = "Compilation omitted (output provided)."
    environ['exec_info'] = {'mode': 'output-only'}
    environ['out_file'] = environ['source_file']
    return environ
