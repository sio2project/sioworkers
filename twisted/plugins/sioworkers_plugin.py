import urlparse
import os
from zope.interface import implements

from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker
from twisted.application import internet

from sio.protocol.worker import WorkerFactory
from filetracker.servers.run import DEFAULT_PORT as DEFAULT_FILETRACKER_PORT


def _host_from_url(url):
    return urlparse.urlparse(url).hostname


class Options(usage.Options):
    #TODO: any other options?
    optParameters = [["port", "p", 7888, "sioworkersd port number"]]

    def parseArgs(self, host):
        self['host'] = host


class SioServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "sio"
    description = "Sioworkers application"
    options = Options

    def makeService(self, options):
        if 'FILETRACKER_URL' not in os.environ:
            default_filetracker_host = None
            if 'CELERY_BROKER_URL' in os.environ:
                default_filetracker_host = \
                        _host_from_url(os.environ['CELERY_BROKER_URL'])
            if not default_filetracker_host:
                default_filetracker_host = '127.0.0.1'
            os.environ['FILETRACKER_URL'] = 'http://%s:%d' \
                    % (default_filetracker_host, DEFAULT_FILETRACKER_PORT)

        return internet.TCPClient(options['host'], int(options["port"]),
                WorkerFactory())


serviceMaker = SioServiceMaker()
