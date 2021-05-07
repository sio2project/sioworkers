from __future__ import absolute_import
from contextlib import contextmanager
import pkg_resources
import time
import logging
import stat
import os
import json
import tempfile
import shutil
import threading
import six

logger = logging.getLogger(__name__)


def first_entry_point(group, name=None):
    for ep in pkg_resources.iter_entry_points(group, name):
        try:
            return ep.load()
        except ImportError as e:
            logger.warning(
                'ImportError: %s: %s'
                % (
                    ep,
                    e,
                )
            )
            pass
    raise RuntimeError("Module providing '%s:%s' not found" % (group, name or ''))


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
    return miliseconds / 1000.0


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


threadlocal_dir = threading.local()


def tempcwd(path=None):
    # Someone might call tempcwd twice, i.e. tempcwd(tempcwd('something'))
    # Do nothing in this case.
    if path is not None and os.path.isabs(path):
        return path
    d = threadlocal_dir.tmpdir
    if path:
        return os.path.join(d, path)
    else:
        return d


class TemporaryCwd(object):
    """Helper class for changing the working directory."""

    def __init__(self, inner_directory=None):
        self.extra = inner_directory
        self.path = None
        self.old_path = None

    def __enter__(self):
        self.path = tempfile.mkdtemp(prefix='sioworkers_')
        logger.info('Using temporary directory %s', self.path)
        p = self.path
        if self.extra:
            p = os.path.join(self.path, self.extra)
            os.mkdir(p)
        self.old_path = getattr(threadlocal_dir, 'tmpdir', None)
        threadlocal_dir.tmpdir = p

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        shutil.rmtree(self.path)
        threadlocal_dir.tmpdir = self.old_path


def path_join_abs(base, subpath):
    """Joins two absolute paths making ``subpath`` relative to ``base``.

    >>> import os.path
    >>> os.path.join('/usr', '/bin/sh')
    '/bin/sh'

    >>> path_join_abs('/usr', '/bin/sh')
    '/usr/bin/sh'
    """
    return os.path.join(base, subpath.strip(os.sep))


def replace_invalid_UTF(a_string):
    """Replaces invalid characters in a string.

    In python 2 strings are also bytestrings.
    In python 3 it returns a string.
    """
    if six.PY2:
        return a_string.decode('utf-8', 'replace').encode('utf-8')
    else:
        if not isinstance(a_string, six.string_types):
            return a_string.decode('utf-8', 'replace')
        else:
            return a_string.encode('utf-8', 'replace').decode()


class CompatibleJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return obj.decode("ASCII")
        return super(CompatibleJSONEncoder, self).default(obj)


def json_dumps(obj, **kwargs):
    """Python 3 and 2 compatible json.dump."""
    kwargs.setdefault('cls', CompatibleJSONEncoder)
    return json.dumps(obj, **kwargs)


def decode_fields(fields):
    def _decode_decorator(func):
        def _wrapper(*args, **kwargs):
            result_dict = func(*args, **kwargs)
            for field in fields:
                if not isinstance(result_dict[field], six.string_types):
                    result_dict[field] = result_dict[field].decode()
            return result_dict

        return _wrapper

    return _decode_decorator


def null_ctx_manager():
    def dummy():
        yield

    return contextmanager(dummy)()


# Copied and stripped from oioioi/base/utils/__init__.py


class ClassInitMeta(type):
    """Meta class triggering __classinit__ on class intialization."""

    def __init__(cls, class_name, bases, new_attrs):
        super(ClassInitMeta, cls).__init__(class_name, bases, new_attrs)
        cls.__classinit__()


class ClassInitBase(six.with_metaclass(ClassInitMeta, object)):
    """Abstract base class injecting ClassInitMeta meta class."""

    @classmethod
    def __classinit__(cls):
        """
        Empty __classinit__ implementation.

        This must be a no-op as subclasses can't reliably call base class's
        __classinit__ from their __classinit__s.

        Subclasses of __classinit__ should look like:

        .. python::

            class MyClass(ClassInitBase):

                @classmethod
                def __classinit__(cls):
                    # Need globals().get as MyClass may be still undefined.
                    super(globals().get('MyClass', cls),
                            cls).__classinit__()
                    ...

            class Derived(MyClass):

                @classmethod
                def __classinit__(cls):
                    super(globals().get('Derived', cls),
                            cls).__classinit__()
                    ...
        """
        pass


class RegisteredSubclassesBase(ClassInitBase):
    """A base class for classes which should have a list of subclasses
    available.

    The list of subclasses is available in their :attr:`subclasses` class
    attributes. Classes which have *explicitly* set :attr:`abstract` class
    attribute to ``True`` are not added to :attr:`subclasses`.

    It the superclass defines :classmethod:`register_subclass` class
    method, then it is called with subclass upon registration.
    """

    @classmethod
    def __classinit__(cls):
        this_cls = globals().get('RegisteredSubclassesBase', cls)
        super(this_cls, cls).__classinit__()
        if this_cls is cls:
            # This is RegisteredSubclassesBase class.
            return

        assert 'subclasses' not in cls.__dict__, (
            '%s defines attribute subclasses, but has '
            'RegisteredSubclassesMeta metaclass' % (cls,)
        )
        cls.subclasses = []
        cls.abstract = cls.__dict__.get('abstract', False)

        def find_superclass(cls):
            superclasses = [c for c in cls.__bases__ if issubclass(c, this_cls)]
            if not superclasses:
                return None
            if len(superclasses) > 1:
                raise AssertionError(
                    '%s derives from more than one '
                    'RegisteredSubclassesBase' % (cls.__name__,)
                )
            superclass = superclasses[0]
            return superclass

        # Add the class to all superclasses' 'subclasses' attribute, including
        # self.
        superclass = cls
        while superclass is not this_cls:
            if not cls.abstract:
                superclass.subclasses.append(cls)
                if hasattr(superclass, 'register_subclass'):
                    superclass.register_subclass(cls)
            superclass = find_superclass(superclass)
