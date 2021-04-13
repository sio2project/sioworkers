from __future__ import absolute_import

from sio.workers.sandbox import Sandbox

import pytest


class SandboxDummy(Sandbox):
    def _get(self):
        raise RuntimeError


def test_setting_in_context():
    try:
        s = SandboxDummy("test")
        with s as _:
            assert False
    except:
        assert s._in_context == 0
