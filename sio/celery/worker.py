"""Command-line script: auto-configured celeryd for sioworkers"""

import os
from optparse import OptionParser
import urlparse
from celery import Celery
from celery.bin.worker import worker
import celery.loaders.default
from filetracker.servers.run import DEFAULT_PORT as DEFAULT_FILETRACKER_PORT

def _host_from_url(url):
    return urlparse.urlparse(url).hostname

def main():
    usage = "usage: %prog [options] [broker-url]"
    epilog = """\
The worker needs Filetracker server configured. If no FILETRACKER_URL is
present in the environment, a sensible default is generated, using the same
host as the Celery broker uses, with default Filetracker port."""
    parser = OptionParser(usage=usage, epilog=epilog)
    parser.disable_interspersed_args()

    os.environ.setdefault('CELERY_CONFIG_MODULE', 'sio.celery.default_config')
    app = Celery()
    cmd = worker(app)
    for x in cmd.get_options():
        parser.add_option(x)

    options, args = parser.parse_args()

    if len(args) > 1:
        parser.error("Unexpected arguments: " + ' '.join(args[1:]))
    if args:
        broker_url = args[0]
        os.environ['CELERY_BROKER_URL'] = args[0]

    return cmd.run(**vars(options))
