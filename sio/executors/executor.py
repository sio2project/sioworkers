from __future__ import absolute_import
from sio.executors import common, encdec_common
from sio.workers.executors import SupervisedExecutor


def run(environ):
    return common.run(environ, SupervisedExecutor())


def encdec_run(environ):
    return encdec_common.run(environ, SupervisedExecutor())
