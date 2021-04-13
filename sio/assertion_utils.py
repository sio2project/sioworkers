from __future__ import absolute_import
import pytest


# Convenience functions for testing


def ok_(expr, msg=None):
    assert expr, msg or '%r does not evaluate to True' % expr


def eq_(a, b, msg=None):
    assert a == b, msg or "%r != %r" % (a, b)


def not_eq_(a, b, msg=None):
    assert a != b, msg or "%r == %r" % (a, b)


def raises(exception):
    """Assert that test is raising an exception
    Usage:

    @raises(SomeException)
    def test_that_should_raise_SomeException(...):
        # ...

    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            with pytest.raises(exception):
                func(*args, **kwargs)

        return wrapper

    return decorator


def assert_raises(exception, func, *args, **kwargs):
    """Assert that function `func` raises `expcetions` when run
    with `*args_list` and `**kwargs_list`.
    """
    with pytest.raises(exception):
        func(*args, **kwargs)


def in_(a, b, msg=None):
    """Shorthand for 'assert a in b, "%r not in %r" % (a, b)"""
    if a not in b:
        raise AssertionError(msg or "%r not in %r" % (a, b))


def not_in_(a, b, msg=None):
    """Shorthand for 'assert a not in b, "%r not in %r" % (a, b)"""
    if a in b:
        raise AssertionError(msg or "%r in %r" % (a, b))


def timed(time):
    return pytest.mark.timeout(time)


def nottest(func):
    return pytest.mark.skip(func)
