from twisted.application import service, internet
from manager import WorkerManager
from scheduler import FIFOScheduler
import evalmgr

top = service.MultiService()

manager = WorkerManager()
manager.setServiceParent(top)

scheduler = FIFOScheduler(manager)
scheduler.setServiceParent(top)

rpc = evalmgr.makeSite(manager, scheduler)
internet.TCPServer(7889, rpc).setServiceParent(top)

internet.TCPServer(7888, manager.makeFactory()).setServiceParent(top)

application = service.Application('sioworkersd')
top.setServiceParent(application)

