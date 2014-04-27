from sio.compilers.system_java import JavaCompiler as UnsafeJavaCompiler


class JavaCompiler(UnsafeJavaCompiler):
    sandbox = 'java.1_8'

    def _execute(self, *args, **kwargs):
        kwargs['proot_options'] = ['-b', '/proc']
        return super(JavaCompiler, self)._execute(*args, **kwargs)


def run(environ):
    return JavaCompiler(sandbox='java.1_8').compile(environ)


run_default = run
