# This file is named twisted_t.py to avoid it being found by nosetests,
# which hangs on some Twisted test cases. Use trial <module>.
from twisted.trial import unittest
from twisted.internet import defer, interfaces
from twisted.application.service import Application
from zope.interface import implementer

from sio.sioworkersd import manager, db, fifo, taskmanager, server
from sio.protocol.rpc import RemoteError
import shutil
import tempfile

# debug
def _print(x):
    print x
    return x


class TestWithDB(unittest.TestCase):
    """Abstract class for testing sioworkersd parts that need a database."""
    SAVED_TASKS = []

    def __init__(self, *args):
        super(TestWithDB, self).__init__(*args)
        self.app = None
        self.db = None
        self.workerm = None
        self.sched = None
        self.taskm = None

    def setUp(self):
        self.db_dir = tempfile.mkdtemp()
        self.db_path = self.db_dir + '/sio_tests.sqlite'

    def tearDown(self):
        shutil.rmtree(self.db_dir)

    def _prepare_svc(self):
        self.app = Application('test')
        self.db = db.DBWrapper(self.db_path)
        self.db.setServiceParent(self.app)
        d = self.db.openDB()
        # HACK: we need to run openDB manually earlier to insert test values
        # but it can't be called a second time in startService
        self.db.openDB = lambda: None

        @defer.inlineCallbacks
        def db_callback(_):
            for tid, env in self.SAVED_TASKS:
                yield self.db.runOperation(
                    "insert into task (id, env) values (?, ?)",
                        (tid, env))
            self.workerm = manager.WorkerManager(self.db)
            self.workerm.setServiceParent(self.db)
            self.sched = fifo.FIFOScheduler(self.workerm)
            self.taskm = taskmanager.TaskManager(self.db, self.workerm,
                    self.sched)
            self.taskm.setServiceParent(self.db)
            yield self.db.startService()
        d.addCallback(db_callback)
        return d

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


@implementer(interfaces.ITransport)
class MockTransport(object):
    def __init__(self):
        self.connected = True

    def loseConnection(self):
        self.connected = False


class TestWorker(server.WorkerServer):
    def __init__(self):
        server.WorkerServer.__init__(self)
        self.name = 'test_worker'
        self.wm = None
        self.transport = MockTransport()

    def call(self, method, *a, **kw):
        if method == 'run':
            env = a[0]
            if env['task_id'].startswith('ok'):
                env['foo'] = 'bar'
                return defer.succeed(env)
            elif env['task_id'] == 'fail':
                return defer.fail(RemoteError('test'))
            elif env['task_id'].startswith('hang'):
                return defer.Deferred()


class WorkerManagerTest(TestWithDB):
    def __init__(self, *args, **kwargs):
        super(WorkerManagerTest, self).__init__(*args, **kwargs)
        self.notifyCalled = False
        self.wm = None
        self.worker_proto = None

    def _notify_cb(self, _):
        self.notifyCalled = True

    def setUp2(self, _=None):
        self.wm = manager.WorkerManager(self.db)
        self.wm.notifyOnNewWorker(self._notify_cb)
        self.worker_proto = TestWorker()
        return self.wm.newWorker('unique1', self.worker_proto)

    def setUp(self):
        super(WorkerManagerTest, self).setUp()
        d = self._prepare_svc()
        d.addCallback(self.setUp2)
        return d

    def test_notify(self):
        self.assertTrue(self.notifyCalled)

    @defer.inlineCallbacks
    def test_run(self):
        yield self.assertIn('test_worker', self.wm.workers)
        ret = yield self.wm.runOnWorker('test_worker', {'task_id': 'ok'})
        yield self.assertIn('foo', ret)
        yield self.assertEqual('bar', ret['foo'])

    def test_fail(self):
        d = self.wm.runOnWorker('test_worker', {'task_id': 'fail'})
        d.addBoth(_print)
        return self.assertFailure(d, RemoteError)

    def test_exclusive(self):
        self.wm.runOnWorker('test_worker', {'task_id': 'hang1'})
        self.assertRaises(RuntimeError,
                self.wm.runOnWorker, 'test_worker', {'task_id': 'hang2'})

    def test_exclusive2(self):
        self.wm.runOnWorker('test_worker',
                {'task_id': 'hang1', 'exclusive': False})
        self.assertRaises(RuntimeError,
                self.wm.runOnWorker, 'test_worker', {'task_id': 'hang2'})

    def test_gone(self):
        d = self.wm.runOnWorker('test_worker', {'task_id': 'hang'})
        self.wm.workerLost(self.worker_proto)
        return self.assertFailure(d, manager.WorkerGone)

    def test_duplicate(self):
        w2 = TestWorker()
        d = self.wm.newWorker('unique2', w2)
        self.assertFalse(w2.transport.connected)
        return self.assertFailure(d, manager.DuplicateWorker)
