from __future__ import absolute_import
from sio.executors import common, interactive_common
from sio.workers.executors import SupervisedExecutor


def run(environ):
    return common.run(environ, SupervisedExecutor())

def interactive_run(environ):
    return interactive_common.run(environ, SupervisedExecutor())
