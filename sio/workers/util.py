import pkg_resources
import time
import logging
import stat
import os
import shutil

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
    """Converts ``seconds`` to miliseconds

       >>> s2ms(1.95)
       1950
    """
    return int(1000 * seconds)

def ms2s(miliseconds):
    """Converts ``miliseconds`` to seconds and returns float.

       >>> '%.2f' % ms2s(1190)
       '1.19'
    """
    return miliseconds / 1000.

def ceil_ms2s(miliseconds):
    """Returns first integer count of seconds not less that ``miliseconds``.

       >>> ceil_ms2s(1000)
       1
       >>> ceil_ms2s(1001)
       2
    """
    return int((miliseconds + 999) / 1000)

class Writable(object):
    """Context manager making file writable.

       It's not safe to use it concurrently on the same file, but nesting is ok.
    """
    def __init__(self, fname):
        self.orig_mode = os.stat(fname).st_mode
        self.change_needed = ~(self.orig_mode & stat.S_IWUSR)
        self.fname = fname

    def __enter__(self):
        if self.change_needed:
            os.chmod(self.fname, self.orig_mode | stat.S_IWUSR)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.change_needed:
            os.chmod(self.fname, self.orig_mode)

def rmtree(path):
    def remove_readonly(fn, path, excinfo):
        with Writable(os.path.normpath(os.path.dirname(path))):
            fn(path)

    shutil.rmtree(path, onerror=remove_readonly)

def path_join_abs(base, subpath):
    """Joins two absolute paths making ``subpath`` relative to ``base``.

       >>> import os.path
       >>> os.path.join('/usr', '/bin/sh')
       '/bin/sh'

       >>> path_join_abs('/usr', '/bin/sh')
       '/usr/bin/sh'
    """
    return os.path.join(base, subpath.strip(os.sep))
