from __future__ import absolute_import
import os

_original_cwd = os.getcwd()


class Failure(Exception):
    """Class used to report errors to the user in jobs.

    This exception should be caught by job runner and not
    cause a non-zero status code, but instead the error
    should be recorded in environment and returned
    as usual.
    """
