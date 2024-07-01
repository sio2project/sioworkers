# Taken from
# https://github.com/gdub/python-archive/blob/master/archive/__init__.py
# Modified

# Copyright (c) Gary Wilson Jr. <gary@thegarywilson.com> and contributors.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import os
import tarfile
import zipfile


class ArchiveException(Exception):
    """Base exception class for all archive errors."""


class UnrecognizedArchiveFormat(ArchiveException):
    """Error raised when passed file is not a recognized archive format."""


class UnsafeArchive(ArchiveException):
    """
    Error raised when passed file contains paths that would be extracted
    outside of the target directory.
    """


def extract(path, member, to_path='', ext='', **kwargs):
    """
    Unpack member from the tar or zip file at the specified path to the directory
    specified by to_path.
    """
    Archive(path, ext=ext).extract(member, to_path, **kwargs)


class Archive(object):
    """
    The external API class that encapsulates an archive implementation.
    """

    def __init__(self, file, ext=''):
        """
        Arguments:
        * 'file' can be a string path to a file or a file-like object.
        * Optional 'ext' argument can be given to override the file-type
          guess that is normally performed using the file extension of the
          given 'file'.  Should start with a dot, e.g. '.tar.gz'.
        """
        self._archive = self._archive_cls(file, ext=ext)(file)

    @staticmethod
    def _archive_cls(file, ext=''):
        """
        Return the proper Archive implementation class, based on the file type.
        """
        filename = None
        if isinstance(file, str):
            filename = file
        else:
            try:
                filename = file.name
            except AttributeError:
                raise UnrecognizedArchiveFormat(
                    "File object not a recognized archive format.")
        for cls in HANDLED_ARCHIVES:
            if cls.is_archive(filename):
                return cls
    
        raise UnrecognizedArchiveFormat(
            "Path not a recognized archive format: %s" % filename)

    def extract(self, *args, **kwargs):
        self._archive.extract(*args, **kwargs)

    def list(self):
        self._archive.list()
    
    def filenames(self):
        return self._archive.filenames()


class BaseArchive(object):
    """
    Base Archive class.  Implementations should inherit this class.
    """
    def __del__(self):
        if hasattr(self, "_archive"):
            self._archive.close()

    def list(self):
        raise NotImplementedError()

    def filenames(self):
        """
        Return a list of the filenames contained in the archive.
        """
        raise NotImplementedError()
    
    @staticmethod
    def is_archive(filename):
        return NotImplementedError()

    def _extract(self, member, to_path):
        """
        Performs the actual extraction.  Separate from 'extract' method so that
        we don't recurse when subclasses don't declare their own 'extract'
        method.
        """
        self._archive.extract(member, path=to_path)

    def extract(self, member, to_path='', method='safe'):
        if method == 'safe':
            self.check_files(to_path)
        elif method == 'insecure':
            pass
        else:
            raise ValueError("Invalid method option")
        self._extract(member, to_path)

    def check_files(self, to_path=None):
        """
        Check that all of the files contained in the archive are within the
        target directory.
        """
        if to_path:
            target_path = os.path.normpath(os.path.realpath(to_path))
        else:
            target_path = os.getcwd()
        for filename in self.filenames():
            extract_path = os.path.join(target_path, filename)
            extract_path = os.path.normpath(os.path.realpath(extract_path))
            if not extract_path.startswith(target_path):
                raise UnsafeArchive(
                    "Archive member destination is outside the target"
                    " directory.  member: %s" % filename)


class TarArchive(BaseArchive):

    def __init__(self, file):
        # tarfile's open uses different parameters for file path vs. file obj.
        if isinstance(file, str):
            self._archive = tarfile.open(name=file)
        else:
            self._archive = tarfile.open(fileobj=file)

    def list(self, *args, **kwargs):
        self._archive.list(*args, **kwargs)

    def filenames(self):
        return self._archive.getnames()

    @staticmethod
    def is_archive(filename):
        return tarfile.is_tarfile(filename)


class ZipArchive(BaseArchive):

    def __init__(self, file):
        # ZipFile's 'file' parameter can be path (string) or file-like obj.
        self._archive = zipfile.ZipFile(file)

    def list(self, *args, **kwargs):
        self._archive.printdir(*args, **kwargs)

    def filenames(self):
        return self._archive.namelist()
    
    @staticmethod
    def is_archive(filename):
        return zipfile.is_zipfile(filename)

HANDLED_ARCHIVES = (ZipArchive, TarArchive)
