from __future__ import absolute_import
from sio.executors import common
from sio.workers.executors import VCPUExecutor

def run(environ):
    return common.run(environ, VCPUExecutor())
