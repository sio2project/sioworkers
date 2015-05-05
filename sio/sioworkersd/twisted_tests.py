from twisted.trial import unittest
from twisted.internet import defer
from twisted.application.service import Application

from sio.sioworkersd import manager, db, fifo, taskmanager, server
import shutil
import tempfile

# debug
def _print(x):
    print x
    return x


class TestWithDB(unittest.TestCase):
    SAVED_TASKS = []
    def setUp(self):
        self.db_dir = tempfile.mkdtemp()
        self.db_path = self.db_dir + '/sio_tests.sqlite'

    def tearDown(self):
        shutil.rmtree(self.db_dir)

    @defer.inlineCallbacks
    def _prepare_svc(self):
        self.app = Application('test')
        self.db = db.DBWrapper(self.db_path)
        self.db.setServiceParent(self.app)
        yield self.db.openDB()
        # HACK: we need to run openDB manually earlier to insert test values
        # but it can't be called a second time in startService
        self.db.openDB = lambda : None
        for tid, env in self.SAVED_TASKS:
            yield self.db.runOperation(
                "insert into task (id, env) values (?, ?)",
                    (tid, env))
        self.workerm = manager.WorkerManager(self.db)
        self.workerm.setServiceParent(self.db)
        self.sched = fifo.FIFOScheduler(self.workerm)
        self.taskm = taskmanager.TaskManager(self.db, self.workerm, self.sched)
        self.taskm.setServiceParent(self.db)
        yield self.db.startService()

class TaskManagerTest(TestWithDB):
    SAVED_TASKS = [
            ('asdf', '{"task_id": "asdf"}')
            ]

    def test_restore(self):
        d = self._prepare_svc()
        d.addCallback(lambda _:
                self.assertIn('asdf', self.taskm.inProgress))
        d.addCallback(lambda _:
                self.assertDictEqual(self.taskm.inProgress['asdf'].env,
                            {'task_id': 'asdf'}))
        return d



class TestWorker(server.WorkerServer):
    def run():
        pass


class WorkerManagerTest(TestWithDB):
    def __init__(self, *args, **kwargs):
        super(WorkerManagerTest, self).__init__(*args, **kwargs)
        self.notifyCalled = False

    def _notify_cb(self, _):
        self.notifyCalled = True

    def setUp2(self, _=None):
        self.wm = manager.WorkerManager(self.db)
        self.wm.notifyOnNewWorker(self._notify_cb)

    def setUp(self):
        super(WorkerManagerTest, self).setUp()
        d = self._prepare_svc()
        d.addCallback(self.setUp2)
        return d

    def test_notify(self):
        w = TestWorker()
        d = self.wm.newWorker('unique1', w)
        d.addCallback(lambda _: self.assertTrue(self.notifyCalled))
        return d
