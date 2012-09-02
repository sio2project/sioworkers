import pkg_resources
import time

def first_entry_point(group, name=None):
    for ep in pkg_resources.iter_entry_points(group, name):
        try:
            return ep.load()
        except ImportError:
            pass
    raise RuntimeError("Module providing '%s:%s' not found" %
            (group, name or ''))

class PerfTimer(object):
    def __init__(self):
        self.start_time = time.time()

    @property
    def elapsed(self):
        return time.time() - self.start_time

