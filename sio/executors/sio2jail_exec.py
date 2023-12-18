from sio.executors import common, encdec_common
from sio.workers.executors import Sio2JailExecutor


def run(environ):
    return common.run(environ, Sio2JailExecutor())


def encdec_run(environ):
    return encdec_common.run(environ, Sio2JailExecutor())
