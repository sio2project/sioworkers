# This file is named twisted_t.py to avoid it being found by nosetests,
# which hangs on some Twisted test cases. Use trial <module>.
from twisted.trial import unittest
from twisted.internet import defer, interfaces, reactor, protocol, task
from twisted.application.service import Application
from zope.interface import implementer

from sio.sioworkersd import workermanager, taskmanager, server
from sio.sioworkersd.scheduler.fifo import FIFOScheduler
from sio.protocol import rpc
import shutil
import tempfile

# debug
def _print(x):
    print x
    return x


def _fill_env(env):
    if 'job_type' not in env:
        env['job_type'] = 'cpu-exec'
    return env

def _wrap_into_group_env(env):
    env['group_id'] = 'asdf_group'
    return {
        'group_id': 'asdf_group',
        'workers_jobs': {
            env['task_id']: env
        }
    }


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
        self.db_path = self.db_dir + '/sio_tests.db'

    def tearDown(self):
        if self.taskm:
            self.taskm.database.db.close()
        shutil.rmtree(self.db_dir)

    def _prepare_svc(self):
        self.app = Application('test')
        self.workerm = workermanager.WorkerManager()
        self.sched = FIFOScheduler(self.workerm)
        self.taskm = taskmanager.TaskManager(self.db_path, self.workerm,
                                             self.sched)
        # HACK: tests needs clear twisted's reactor, so we're mocking
        #       method that creates additional deferreds.
        self.taskm.database.start_periodic_sync = lambda: None

        for tid, env in self.SAVED_TASKS:
            self.taskm.database.update(tid, env)

        return self.taskm.startService()

class TaskManagerTest(TestWithDB):
    SAVED_TASKS = [
        ('asdf_group', {
            "id": "asdf_group",
            "status": "to_judge",
            "timestamp": "1491407526.72",
            "retry_cnt": 0,
            "env": {
                "group_id": "asdf_group",
                "return_url": "localhost",
                "workers_jobs": {
                    "asdf": {
                        "task_id": "asdf",
                        "group_id": "asdf_group",
                        "job_type": "cpu-exec"
                    }
                }
            }
        })
    ]

    def test_restore(self):
        d = self._prepare_svc()
        d.addCallback(lambda _:
                self.assertIn('asdf', self.taskm.inProgress))
        d.addCallback(lambda _:
                self.assertDictEqual(self.taskm.inProgress['asdf'].env,
                        {'task_id': 'asdf', 'job_type': 'cpu-exec',
                         'group_id': 'asdf_group',
                         'contest_uid': (None, None)}))
        return d


@implementer(interfaces.ITransport)
class MockTransport(object):
    def __init__(self):
        self.connected = True

    def loseConnection(self):
        self.connected = False


class TestWorker(server.WorkerServer):
    def __init__(self, clientInfo=None):
        server.WorkerServer.__init__(self)
        self.wm = None
        self.transport = MockTransport()
        self.running = []
        if not clientInfo:
            self.name = 'test_worker'
            self.clientInfo = {'name': self.name,
                    'concurrency': 2, 'can_run_cpu_exec': True}
        else:
            self.name = clientInfo['name']
            self.clientInfo = clientInfo

    def call(self, method, *a, **kw):
        if method == 'run':
            env = a[0]
            if env['task_id'].startswith('ok'):
                env['foo'] = 'bar'
                return defer.succeed(env)
            elif env['task_id'] == 'fail':
                return defer.fail(rpc.RemoteError('test'))
            elif env['task_id'].startswith('hang'):
                return defer.Deferred()
        elif method == 'get_running':
            return self.running


class WorkerManagerTest(TestWithDB):
    def __init__(self, *args, **kwargs):
        super(WorkerManagerTest, self).__init__(*args, **kwargs)
        self.notifyCalled = False
        self.wm = None
        self.worker_proto = None

    def _notify_cb(self, _):
        self.notifyCalled = True

    def setUp2(self, _=None):
        self.wm = workermanager.WorkerManager()
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
        ret = yield self.wm.runOnWorker('test_worker',
                _fill_env({'task_id': 'ok'}))
        yield self.assertIn('foo', ret)
        yield self.assertEqual('bar', ret['foo'])

    def test_fail(self):
        d = self.wm.runOnWorker('test_worker', _fill_env({'task_id': 'fail'}))
        d.addBoth(_print)
        return self.assertFailure(d, rpc.RemoteError)

    def test_cpu_exec(self):
        self.wm.runOnWorker('test_worker', _fill_env({'task_id': 'hang1'}))
        self.assertRaises(RuntimeError,
                self.wm.runOnWorker, 'test_worker',
                _fill_env({'task_id': 'hang2'}))

    def test_cpu_exec2(self):
        self.wm.runOnWorker('test_worker',
                _fill_env({'task_id': 'hang1', 'job-type': 'vcpu-exec'}))
        self.assertRaises(RuntimeError,
                self.wm.runOnWorker, 'test_worker',
                _fill_env({'task_id': 'hang2'}))

    def test_gone(self):
        d = self.wm.runOnWorker('test_worker',
                _fill_env({'task_id': 'hang', 'job_type': 'cpu-exec'}))
        self.wm.workerLost(self.worker_proto)
        return self.assertFailure(d, workermanager.WorkerGone)

    def test_duplicate(self):
        w2 = TestWorker()
        d = self.wm.newWorker('unique2', w2)
        self.assertFalse(w2.transport.connected)
        return self.assertFailure(d, server.DuplicateWorker)

    def test_rejected(self):
        w2 = TestWorker()
        w2.running = ['asdf']
        w2.name = 'name2'
        d = self.wm.newWorker('unique2', w2)
        return self.assertFailure(d, server.WorkerRejected)

    def test_reject_incomplete_worker(self):
        w3 = TestWorker({'name': 'no_concurrency'})
        d = self.wm.newWorker('no_concurrency', w3)
        self.assertFailure(d, server.WorkerRejected)

        w4 = TestWorker({'name': 'unique4', 'concurrency': 'not a number'})
        d = self.wm.newWorker('unique4', w4)
        self.assertFailure(d, server.WorkerRejected)

        w5 = TestWorker({'name': 'unique5', 'can_run_cpu_exec': 'not boolean'})
        d = self.wm.newWorker('unique5', w5)
        self.assertFailure(d, server.WorkerRejected)


class TestClient(rpc.WorkerRPC):
    def __init__(self, running, can_run_cpu_exec=True, name='test'):
        rpc.WorkerRPC.__init__(self, server=False)
        self.running = running
        self.can_run_cpu_exec = can_run_cpu_exec
        self.name = name

    def getHelloData(self):
        return {'name': self.name, 'concurrency': 1,
                'can_run_cpu_exec': self.can_run_cpu_exec}

    def cmd_get_running(self):
        return list(self.running)

    def do_run(self, env):
        if env['task_id'].startswith('hang'):
            return defer.Deferred()
        else:
            return defer.succeed(env)

    def cmd_run(self, env):
        self.running.add(env['task_id'])
        d = self.do_run(env)

        def _rm(x):
            self.running.remove(env['task_id'])
            return x
        d.addBoth(_rm)
        return d

class IntegrationTest(TestWithDB):
    def __init__(self, *args, **kwargs):
        super(IntegrationTest, self).__init__(*args, **kwargs)
        self.notifyCalled = False
        self.wm = None
        self.taskm = None
        self.port = None

    def setUp2(self, _=None):
        workermanager.TASK_TIMEOUT = 3
        self.wm = workermanager.WorkerManager()
        self.sched = FIFOScheduler(self.wm)
        self.taskm = taskmanager.TaskManager(self.db, self.wm, self.sched)

        # Normally added by startService()
        self.wm.notifyOnNewWorker(lambda name: self.taskm._tryExecute())

        factory = self.wm.makeFactory()
        self.port = reactor.listenTCP(0, factory, interface='127.0.0.1')
        self.addCleanup(self.port.stopListening)

    def setUp(self):
        super(IntegrationTest, self).setUp()
        d = self._prepare_svc()
        d.addCallback(self.setUp2)
        return d

    def _wrap_test(self, callback, callback_args, *client_args):
        creator = protocol.ClientCreator(reactor, TestClient, *client_args)

        def cb(client):
            self.addCleanup(client.transport.loseConnection)
            # We have to wait for a few (local) network roundtrips, hence the
            # magic one-second delay.
            return task.deferLater(
                    reactor, 1, callback, client, **callback_args)
        return creator.connectTCP('127.0.0.1', self.port.getHost().port).\
                addCallback(cb)

    def test_remote_run(self):
        def cb(client):
            self.assertIn('test', self.wm.workers)
            d = self.taskm.addTaskGroup(
                    _wrap_into_group_env(_fill_env({'task_id': 'asdf'})))
            d.addCallback(lambda x: self.assertIn('workers_jobs', x) and
                        self.assertIn('asdf', x['workers_jobs']) and
                        self.assertIn('task_id', x['workers_jobs']['asdf']))
            return d
        return self._wrap_test(cb, {}, set())

    def test_timeout(self):
        def cb3(_):
            self.assertEqual(self.wm.workers, {})

        def cb2(_, client):
            return task.deferLater(reactor, 2, cb3, client)

        def cb(client):
            d = self.taskm.addTaskGroup(
                    _wrap_into_group_env(_fill_env({'task_id': 'hang'})))
            d = self.assertFailure(d, rpc.TimeoutError)
            d.addBoth(cb2, client)
            return d
        return self._wrap_test(cb, {}, set())

    def test_gone(self):
        def cb3(client, d):
            self.assertFalse(d.called)
            self.assertDictEqual(self.wm.workers, {})
            self.assertEqual(self.sched.queues['cpu+vcpu'][-1][0], 'hang')
            self.assertEqual(len(self.sched.queues['cpu+vcpu']), 1)

        def cb2(client, d):
            client.transport.loseConnection()
            # Wait for the connection to drop
            return task.deferLater(reactor, 1, cb3, client, d)

        def cb(client):
            d = self.taskm.addTaskGroup(
                    _wrap_into_group_env(_fill_env({'task_id': 'hang'})))
            # Allow the task to schedule
            return task.deferLater(reactor, 0, cb2, client, d)
        return self._wrap_test(cb, {}, set())

    def test_cpu_exec(self):
        def cb4(d):
            self.assertTrue(d.called)

        def cb3(client, d):
            self.assertIn('test1', self.wm.workers)
            self.assertIn('test2', self.wm.workers)
            return task.deferLater(reactor, 1, cb4, d)

        def cb2(d):
            self.assertIn('test1', self.wm.workers)
            self.assertFalse(d.called)
            return self._wrap_test(cb3, {'d': d}, set(), True, 'test2')

        def cb(client):
            d = self.taskm.addTaskGroup(
                    _wrap_into_group_env(
                        _fill_env({'task_id': 'asdf',
                                   'job_type': 'cpu-exec'})))
            d.addCallback(lambda x: self.assertIn('workers_jobs', x) and
                        self.assertIn('asdf', x['workers_jobs']) and
                        self.assertIn('task_id', x['workers_jobs']['asdf']))
            return task.deferLater(reactor, 1, cb2, d)
        return self._wrap_test(cb, {}, set(), False, 'test1')
