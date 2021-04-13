from __future__ import absolute_import
import os
import six.moves.urllib.error
import six.moves.urllib.parse
import six.moves.urllib.request
import time
import shutil
import logging
import threading
import hashlib

from filetracker.client import Client as FiletrackerClient
from sio.workers import _original_cwd, util

logger = logging.getLogger(__name__)
lock = threading.Lock()

# We don't want to create new client everytime a run(environ) is called so
# we cache clients in dict
ft_clients = dict()


def get_url_hash(filetracker_url):
    return hashlib.md5(filetracker_url).hexdigest()


def get_cache_dir(filetracker_url):
    folder_name = 'ft_cache_' + get_url_hash(filetracker_url)
    return os.path.expanduser(os.path.join('~', '.filetracker_cache', folder_name))


# This function is called at the beginning of run(environ) to
# set thread local client instance (stored in _instance).
# Every Client has to have seperate cache folder
def init_instance(filetracker_url):
    url_hash = get_url_hash(filetracker_url)
    lock.acquire()
    if not url_hash in ft_clients:
        ft_clients[url_hash] = FiletrackerClient(
            remote_url=filetracker_url, cache_dir=get_cache_dir(filetracker_url)
        )

    util.threadlocal_dir.ft_client_instance = ft_clients[url_hash]
    lock.release()


def instance():
    """Returns a singleton instance of :class:`filetracker.client.Client`."""
    if getattr(util.threadlocal_dir, 'ft_client_instance', None) is None:
        launch_filetracker_server()
        util.threadlocal_dir.ft_client_instance = FiletrackerClient()
    return util.threadlocal_dir.ft_client_instance


def set_instance(client):
    """Sets the singleton :class:`filetracker.client.Client` to the given
    object."""
    util.threadlocal_dir.ft_client_instance = client


def _use_filetracker(name, environ):
    mode = environ.get('use_filetracker', True)
    if mode == 'auto':
        return name.startswith('/')
    return bool(mode)


def download(environ, key, dest=None, skip_if_exists=False, **kwargs):
    """Downloads the file from ``environ[key]`` and saves it to ``dest``.

    ``dest``
      A filename, directory name or ``None``. In the two latter cases,
      the file is named the same as in ``environ[key]``.

    ``skip_if_exists``
      If ``True`` and ``dest`` points to an existing file (not a directory
      or ``None``), then the file is not downloaded.

    ``**kwargs``
      Passed directly to :meth:`filetracker.client.Client.get_file`.

    The value under ``environ['use_filetracker']`` affects downloading
    in the followins way:

    * if ``True``, nothing special happens

    * if ``False``, the file is not downloaded from filetracker, but the
      passed path is assumed to be a regular filesystem path

    * if ``'auto'``, the file is assumed to be a local filename only if
      it is a relative path (this is usually the case when developers play).

    Returns the path to the saved file.
    """

    if dest and skip_if_exists and os.path.exists(util.tempcwd(dest)):
        return dest
    source = environ[key]
    if dest is None:
        dest = os.path.split(source)[1]
    elif dest.endswith(os.sep):
        dest = os.path.join(dest, os.path.split(source)[1])

    dest = util.tempcwd(dest)
    if not _use_filetracker(source, environ):
        source = os.path.join(_original_cwd, source)
        if not os.path.exists(dest) or not os.path.samefile(source, dest):
            shutil.copy(source, dest)
    else:
        kwargs.setdefault('add_to_cache', False)
        logger.debug("Downloading %s", source)
        perf_timer = util.PerfTimer()
        instance().get_file(source, dest, **kwargs)
        logger.debug(" completed in %.2fs", perf_timer.elapsed)
    return dest


def upload(environ, key, source, dest=None, **kwargs):
    """Uploads the file from ``source`` to filetracker under ``environ[key]``
    name.

    ``source``
      Filename to upload.

    ``dest``
      A filename, directory name or ``None``. In the two latter cases,
      the file is named the same as in ``environ[key]``.

    ``**kwargs``
      Passed directly to :meth:`filetracker.client.Client.put_file`.

    See the note about ``environ['use_filetracker']`` in
    :func:`sio.workers.ft.download`.

    Returns the filetracker path to the saved file.
    """

    if dest is None or key in environ:
        dest = environ[key]
    elif dest.endswith(os.sep):
        dest = os.path.join(dest, os.path.split(source)[1])
    if not _use_filetracker(dest, environ):
        dest = os.path.join(_original_cwd, dest)
        if not os.path.exists(dest) or not os.path.samefile(source, dest):
            shutil.copy(source, dest)
    else:
        logger.debug("Uploading %s", dest)
        perf_timer = util.PerfTimer()
        dest = instance().put_file(dest, source, **kwargs)
        logger.debug(" completed in %.2fs", perf_timer.elapsed)
    environ[key] = dest
    return dest


def _do_launch():
    saved_environ = os.environ.copy()
    try:
        # During cleanup Hudson kills all processes with the following
        # environment variables set appropriately. We do not want
        # the filetracker server to be killed, hence we unset those
        # temporarily.
        for var in (
            'HUDSON_SERVER_COOKIE',
            'BUILD_NUMBER',
            'BUILD_ID',
            'BUILD_TAG',
            'JOB_NAME',
        ):
            del os.environ[var]

        from filetracker.servers.run import main

        main(['-l', '0.0.0.0'])
        time.sleep(5)
    finally:
        os.environ = saved_environ


def launch_filetracker_server():
    """Launches the Filetracker server if ``FILETRACKER_PUBLIC_URL`` is present
    in ``os.environ`` and the server does not appear to be running.

    The server is run in the background and the function returns once the
    server is up and running.
    """

    if 'FILETRACKER_PUBLIC_URL' not in os.environ:
        return
    public_url = os.environ['FILETRACKER_PUBLIC_URL'].split()[0]
    try:
        six.moves.urllib.request.urlopen(public_url + '/status')
        return
    except six.moves.urllib.error.URLError as e:
        logger.info('No Filetracker at %s (%s), launching', public_url, e)
        _do_launch()


if __name__ == '__main__':
    launch_filetracker_server()
