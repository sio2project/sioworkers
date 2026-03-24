from __future__ import absolute_import
from sio.compilers.system_java import JavaCompiler as UnsafeJavaCompiler
from sio.workers.executors import PRoot32BitExecutor


class JavaCompiler(UnsafeJavaCompiler):
    def _execute(self, *args, **kwargs):
        kwargs['binds'] = [('/proc', '/proc', 'rw')]
        return super(JavaCompiler, self)._execute(*args, **kwargs)

    @classmethod
    def java1_8(cls):
        return cls('java.1_8', executor=PRoot32BitExecutor)


def run_java_default(environ):
    return JavaCompiler().java1_8().compile(environ)


def run_java1_8(environ):
    return JavaCompiler().java1_8().compile(environ)


run_java_default = run_java_default
run_java1_8 = run_java1_8
