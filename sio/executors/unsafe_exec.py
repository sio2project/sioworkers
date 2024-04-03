from __future__ import absolute_import
from sio.executors import common, interactive_common
from sio.workers.executors import DetailedUnprotectedExecutor


def run(environ):
    return common.run(environ, DetailedUnprotectedExecutor(), use_sandboxes=False)

def run_interactive(environ):
    return interactive_common.run(environ, DetailedUnprotectedExecutor(), use_sandboxes=False)
