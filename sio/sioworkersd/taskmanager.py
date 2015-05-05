from twisted.application.service import Service
from twisted.internet import defer, reactor
from twisted.internet.task import deferLater
from twisted.python.failure import Failure
from twisted.web import client
from twisted.web.http_headers import Headers
from collections import namedtuple
import json
from StringIO import StringIO
from poster import encode
from sio.sioworkersd.manager import WorkerGone

Task = namedtuple('Task', 'env d')

# How many seconds to wait between task return attempts
RETRY_DELAY = 5
MAX_RETRIES = 60 * 60 / RETRY_DELAY

class TaskManager(Service):
    def __init__(self, db, workerm, sched):
        self.workerm = workerm
        self.database = db
        self.scheduler = sched
        self.inProgress = {}
        # If a connection pool and/or keepalive is necessary
        # in the future, add it here.
        self.agent = client.Agent(reactor)

    @defer.inlineCallbacks
    def startService(self):
        print 'Starting task manager...'
        yield Service.startService(self)
        jobs = yield self.database.runQuery(
            'select id,env,is_group from task order by datetime(time) asc')
        if len(jobs) > 0:
            print "Unfinished jobs found in database, resuming them..."
        for (task_id, env, is_group) in jobs:
            env = json.loads(env)
            if is_group:
                d = self._addGroup(env)
            else:
                self.scheduler.addTask(env)
                d = self._deferTask(env)
            if env.get('return_url'):
                print 'add with returl', task_id
                d.addBoth(self.return_to_sio, url=env['return_url'],
                        orig_env=env, tid=task_id)
            else:
                def _error(x):
                    print "Saved synchronous task failed:", x
                d.addErrback(_error)

        returns = yield self.database.runQuery('select * from return_task')
        for task_id, env, count in returns:
            env = json.loads(env)
            if env.get('return_url'):
                print "Trying again to return old task", task_id
                self.return_to_sio(env, url=env['return_url'],
                        orig_env=env, tid=task_id, count=count)
            else:
                # Can't do anything meaningful, so just log
                print "return_task table contains task without return_url.", \
                        "This should not happen."
                # forget about this return
                yield self._returnDone(None, task_id)
        self.workerm.notifyOnNewWorker(lambda name: self._tryExecute())
        self._tryExecute()

    def _tryExecute(self, x=None):
        # Note: this function might be called _very_ often, which might be
        # a performance problem for complex schedulers, especially during
        # rejudges. A solution exists, but it is a bit complex.
        jobs = self.scheduler.schedule()
        for (task_id, worker) in jobs:
            task = self.inProgress[task_id]
            d = self.workerm.runOnWorker(worker, task.env)

            def _retry_on_disconnect(failure, task_id=task_id, task=task):
                failure.trap(WorkerGone)
                # someone could write a scheduler that requires this
                self.scheduler.delTask(task_id)
                self.scheduler.addTask(task.env)
                self._tryExecute()
            d.addErrback(_retry_on_disconnect)
            d.chainDeferred(task.d)
        # Return the argument to allow this function to be used
        # as a (transparent) callback
        return x

    @defer.inlineCallbacks
    def _taskDone(self, x, tid, save=True):
        if save and 'return_url' in self.inProgress[tid].env:
            yield self.database.runOperation(
                    "insert into return_task (id, env) values (?, ?);",
                    (tid, json.dumps(self.inProgress[tid].env)))
        del self.inProgress[tid]
        self.scheduler.delTask(tid)
        if save:
            yield self.database.runOperation(
                    "delete from task where id = ?", (tid,))
        print tid, 'finished.'
        self._tryExecute()
        defer.returnValue(x)

    def _deferTask(self, env, group=False):
        tid = env['task_id']
        if tid in self.inProgress:
            raise RuntimeError('Tried to add same task twice')
        d = defer.Deferred()
        self.inProgress[tid] = Task(env=env, d=d)

        d.addBoth(self._taskDone, tid=tid, save=not group)
        return d

    def getQueue(self):
        return unicode(self.scheduler)

    @defer.inlineCallbacks
    def addTask(self, task):
        yield self.database.runOperation(
                "insert into task (id, env) values (?, ?)",
                (task['task_id'], json.dumps(task)))
        self.scheduler.addTask(task)
        d = self._deferTask(task)
        self._tryExecute()
        ret = yield d
        defer.returnValue(ret)

    def _addGroup(self, group_env):
        singleTasks = []
        idMap = {}
        for k, v in group_env['workers_jobs'].iteritems():
            idMap[v['task_id']] = k
            self.scheduler.addTask(v)
            singleTasks.append(self._deferTask(v, group=True))
        self.inProgress[group_env['group_id']] = Task(group_env, None)
        d = defer.DeferredList(singleTasks, consumeErrors=True)
        self._tryExecute()

        def _collect(x):
            ret = {}
            failed = []
            for success, result in x:
                if success:
                    #ret.append(result)
                    ret[idMap[result['task_id']]] = result
                else:
                    failed.append(result)
                    result.printTraceback()
                    #ret.append({'error': repr(result)})
            group_env['workers_jobs.results'] = ret
            if failed:
                raise RuntimeError(repr(failed))
            return group_env

        d.addCallback(_collect)
        d.addBoth(self._taskDone, tid=group_env['group_id'])
        return d

    @defer.inlineCallbacks
    def addTaskGroup(self, group_env):
        yield self.database.runOperation(
                "insert into task (id, env, is_group) values (?, ?, 1)",
                (group_env['group_id'], json.dumps(group_env)))
        ret = yield self._addGroup(group_env)
        defer.returnValue(ret)

    def return_to_sio(self, x, url, orig_env=None, tid=None, count=0):
        error = None
        if isinstance(x, Failure):
            assert orig_env
            env = orig_env
            error = {'message': x.getErrorMessage(),
                    'traceback': x.getTraceback()}
            print 'Returning with error:', x.printTraceback()
        else:
            env = x

        if error:
            env['error'] = error
        bodygen, hdr = encode.multipart_encode({
                        'data': json.dumps(env)})
        body = ''.join(bodygen)

        if not tid:
            tid = env.get('task_id', env['group_id'])

        headers = Headers({'User-Agent': ['sioworkersd']})
        for k, v in hdr.iteritems():
            headers.addRawHeader(k, v)

        def do_return():
            # This looks a bit too complicated for just POSTing a string,
            # but there seems to be no other way. Blame Twisted.
            producer = client.FileBodyProducer(StringIO(body))
            d = self.agent.request('POST', url.encode('utf-8'),
                    headers, producer)

            @defer.inlineCallbacks
            def _response(r):
                if r.code != 200:
                    print 'return error:',\
                            'server responded with status code %d' % r.code
                    print 'Response body follows...'
                    bodyD = yield client.readBody(r)
                    print bodyD
                    raise RuntimeError('Failed to return task')
            d.addCallback(_response)
            return d
        ret = do_return()

        def _updateCount(x, n):
            d = self.database.runOperation(
                    'update return_task set count = ? where id = ?;', (n, tid))
            d.addBoth(lambda _: x)
            return d

        def retry(err, r_count):
            if r_count >= MAX_RETRIES:
                print 'Failed to return %s %d times, giving up.' % \
                        (tid, r_count)
                return
            print 'Returning %s to url %s failed, retrying[%d]...' % \
                    (tid, url, r_count)
            print 'error was:', err
            d = deferLater(reactor, RETRY_DELAY, do_return)
            print 'add updc'
            d.addBoth(_updateCount, n=r_count)
            d.addErrback(retry, r_count + 1)
            return d
        ret.addErrback(retry, r_count=count)
        ret.addBoth(self._returnDone, tid=tid)
        return ret

    def _returnDone(self, _, tid):
        return self.database.runOperation(
                "delete from return_task where id = ?;", ((tid,)))
