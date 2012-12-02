import pkg_resources
import time
import logging

logger = logging.getLogger(__name__)

def first_entry_point(group, name=None):
    for ep in pkg_resources.iter_entry_points(group, name):
        try:
            return ep.load()
        except ImportError as e:
            logger.warning('ImportError: %s: %s' % (ep, e,))
            pass
    raise RuntimeError("Module providing '%s:%s' not found" %
            (group, name or ''))

class PerfTimer(object):
    def __init__(self):
        self.start_time = time.time()

    @property
    def elapsed(self):
        return time.time() - self.start_time

def s2ms(seconds):
    """Converts ``seconds`` to miliseconds"""
    return int(1000 * seconds)

def ms2s(miliseconds):
    """Converts ``miliseconds`` to seconds and returns float."""
    return miliseconds / 1000.

def ceil_ms2s(miliseconds):
    """Returns first integer count of seconds not less that ``miliseconds``"""
    return int((miliseconds + 999) / 1000)

