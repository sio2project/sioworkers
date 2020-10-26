import traceback
from twisted.application.service import Service
from twisted.internet import defer, reactor
from twisted.internet.task import deferLater, LoopingCall
from twisted.python.failure import Failure
from twisted.web import client
from twisted.web.http_headers import Headers
from collections import namedtuple
import bsddb
import json
from StringIO import StringIO
from poster import encode
import time
from operator import itemgetter
from sio.protocol.rpc import RemoteError
from sio.sioworkersd.utils import get_required_ram_for_job
from sio.sioworkersd.workermanager import WorkerGone
from twisted.logger import Logger, LogLevel

log = Logger()

Task = namedtuple('Task', 'env d')

MAX_RETRIES_OF_RESULT_RETURNING = 6
# How many seconds wait between following retry attempts.
RETRY_DELAY_OF_RESULT_RETURNING = \
    [10 ** i for i in range(1, MAX_RETRIES_OF_RESULT_RETURNING + 1)]
DB_SYNC_INTERVAL_IN_SEC = 10
# Should not be too small. We want to avoid lots of errors in case of server
# failure.
DB_SYNC_RESTART_INTERVAL_IN_SEC = 60 * 60


class MultiException(Exception):
    def __init__(self, desc, excs):
        s = desc + '\n\n'
        l = []
        for (e, tb) in excs:
            l.append((u"Exception: %s\n%s" % (e, tb)).encode('utf-8'))
        s += ('='*80 + '\n').join(l)
        super(MultiException, self).__init__(s)


class DBWrapper(object):
    def __init__(self, db_filename):
        # hashopen, cause we operate on single keys and do full scan at start.
        self.db = bsddb.hashopen(db_filename)
        # For better performance we are allowing some tasks to be executed
        # multiple times in case of server failure. Hence, we are skipping
        # specific database sync and doing it later with LoopingCall.
        self.db_sync_task = LoopingCall(self.db.sync)

    def start_periodic_sync(self):
        def restart_db_sync_task(failure, task):
            log.error("Failed to sync database. Error:", failure)
            d = deferLater(reactor, DB_SYNC_RESTART_INTERVAL_IN_SEC,
                           lambda: task.start(DB_SYNC_INTERVAL_IN_SEC))
            d.addErrback(restart_db_sync_task, task=task)
            return d
        self.db_sync_task.start(DB_SYNC_INTERVAL_IN_SEC) \
                         .addErrback(restart_db_sync_task,
                                     task=self.db_sync_task)

    def get_items(self):
        items = []
        error = []
        for k in self.db.keys():
            try:
                items.append(json.loads(self.db[k]))
            except:
                error.append(k)
                log.error("Failed to decode {key}", key=k)
        for k in error:
            log.error("Removing {key}", key=k)
            #del self.db[k]
        return items

    def update(self, job_id, dict_update, sync=True):
        job = json.loads(self.db.get(str(job_id), '{}'))
        job.update(dict_update)
        self.db[str(job_id)] = json.dumps(job)
        if sync:
            self.db.sync()

    def delete(self, job_id, sync=False):
        # Check self.db_sync_task to know why sync is False by default
        del self.db[job_id]
        if sync:
            self.db.sync()


class TaskManager(Service):
    def __init__(self, db_filename, workerm, sched, max_task_ram_mb):
        self.workerm = workerm
        self.database = DBWrapper(db_filename)
        self.scheduler = sched
        self.max_task_ram_mb = max_task_ram_mb
        self.inProgress = {}
        # If a connection pool and/or keepalive is necessary
        # in the future, add it here.
        self.agent = client.Agent(reactor)

    @defer.inlineCallbacks
    def startService(self):
        log.info('Starting task manager...')
        yield Service.startService(self)
        self.database.start_periodic_sync()
        all_jobs = self.database.get_items()
        all_jobs.sort(key=itemgetter('timestamp'))

        if len(all_jobs) > 0:
            log.info("Unfinished jobs found in database, resuming them...")

        return_old_task_concurrency = 16
        jobs_to_return = [ [] for _ in range(return_old_task_concurrency) ]
        j = 0

        for job in all_jobs:
            if job['status'] == 'to_judge':
                d = self._addGroup(job['env'])
                log.debug("added again unfinished task {tid}", tid=job['id'])
                d.addBoth(self.returnToSio, url=job['env']['return_url'],
                          orig_env=job['env'], tid=str(job['id']))
            elif job['status'] == 'to_return':
                jobs_to_return[j].append(job)
                j = (j + 1) % return_old_task_concurrency

        for i in range(return_old_task_concurrency):
            log.warn("Returning {n} tasks", n=len(jobs_to_return[i]))
            def return_old_task(x, i, jobs):
                if len(jobs) != 0:
                    job = jobs.pop()
                    log.warn("Trying again to return old task {tid} from {qid}",
                             tid=job['id'], qid=i)
                    d = self.returnToSio(job['env'], url=job['env']['return_url'],
                                           orig_env=job['env'], tid=str(job['id']),
                                           count=job['retry_cnt'])
                    d.addBoth(return_old_task, i=i, jobs=jobs)
            return_old_task(None, i=i, jobs=jobs_to_return[i])

        self.workerm.notifyOnNewWorker(self._newWorker)
        self.workerm.notifyOnLostWorker(self._lostWorker)
        self._tryExecute()

    def _newWorker(self, name):
        self.scheduler.addWorker(name)
        self._tryExecute()

    def _lostWorker(self, name):
        self.scheduler.delWorker(name)
        self._tryExecute()

    def _tryExecute(self, x=None):
        # Note: this function might be called _very_ often, which might be
        # a performance problem for complex schedulers, especially during
        # rejudges. A solution exists, but it is a bit complex.
        jobs = self.scheduler.schedule()
        if len(jobs) > 0:
            log.warn("jobs: {}, inProgress: {}".format(len(jobs), len(self.inProgress)))

        for (task_id, worker) in jobs:
            task = self.inProgress[task_id]
            d = self.workerm.runOnWorker(worker, task.env)

            def _retry_on_disconnect(failure, task_id=task_id, task=task):
                exc = failure.check(WorkerGone)
                # Handle WorkerGone and don't return anything. For other
                # exceptions, errback the original Deferred.
                if exc is None:
                    return task.d.errback(failure)
                log.warn('Worker executing task {t} disappeared. '
                         'Will retry on another.', t=task_id)
                # someone could write a scheduler that requires this
                self.scheduler.delTask(task_id)
                self.scheduler.addTask(task.env)

            # chain manually - we don't want to errback d when retrying
            d.addCallbacks(task.d.callback, _retry_on_disconnect)
        # Return the argument to allow this function to be used
        # as a (transparent) callback
        return x

    def _taskDone(self, x, tid):
        tid = str(tid)
        if isinstance(x, Failure):
            self.inProgress[tid].env['error'] = {
                'message': x.getErrorMessage(),
                'traceback': x.getTraceback()
            }
        # There is no need to save synchronous task. In case of server
        # failure client is disconnected, so it can't receive the result
        # anyway.
        save = 'return_url' in self.inProgress[tid].env
        if save:
            self.database.update(tid, {
                'env': self.inProgress[tid].env,
                'status': 'to_return',
            }, sync=False)
            # No db sync here, because we are allowing some jobs to be done
            # multiple times in case of server failure for better performance.
            # It should be synced soon with other task
            # or `self.database` itself.
        if self.inProgress[tid].env.get('group_id') != tid:
            self.scheduler.delTask(tid)
        del self.inProgress[tid]
        log.info("Task {tid} finished.", tid=tid)
        self._tryExecute()
        return x

    def _deferTask(self, env):
        tid = env['task_id']
        tid = str(tid)
        if tid in self.inProgress:
            raise RuntimeError('Tried to add same task twice')
        d = defer.Deferred()
        log.warn("adding task, inProgress {}".format(len(self.inProgress)))
        self.inProgress[tid] = Task(env=env, d=d)

        d.addBoth(self._taskDone, tid=tid)
        return d

    def getQueue(self):
        return self.scheduler.dump()

    def _addGroup(self, group_env):
        singleTasks = []
        idMap = {}
        contest_uid = (group_env.get('oioioi_instance'),
            group_env.get('contest_id'))
        self.scheduler.updateContest(contest_uid,
            group_env.get('contest_priority', 0),
            group_env.get('contest_weight', 1))
        for k, v in group_env['workers_jobs'].iteritems():
            v['contest_uid'] = contest_uid
            idMap[v['task_id']] = k
            self.scheduler.addTask(v)
            singleTasks.append(self._deferTask(v))
        self.inProgress[group_env['group_id']] = Task(group_env, None)
        d = defer.DeferredList(singleTasks, consumeErrors=True)
        self._tryExecute()

        def _collect(x):
            ret = {}
            failed = []  # list of tuples (exception, traceback string)
            for success, result in x:
                if success:
                    ret[idMap[result['task_id']]] = result
                else:
                    if issubclass(result.type, RemoteError):
                        if result.value.traceback is None:
                            tb = ""
                        else:
                            tb = "Remote traceback:\n" + result.value.traceback
                    else:
                        tb = result.getTraceback()
                    failed.append((result.value, tb))
            group_env['workers_jobs.results'] = ret
            if failed:
                raise MultiException("Some tasks in a group failed.", failed)
            return group_env

        d.addCallback(_collect)
        d.addBoth(self._taskDone, tid=group_env['group_id'])
        return d

    @defer.inlineCallbacks
    def addTaskGroup(self, group_env):
        # Start with validating the tasks.
        for _, task_env in group_env['workers_jobs'].iteritems():
            valid, error = self._isTaskValid(task_env)
            if not valid:
                group_env['error'] = {
                    'message': error,
                    'traceback': traceback.format_exc(),
                }
                defer.returnValue(group_env)
                return

        # There is no need to save synchronous task. In case of server
        # failure client is disconnected, so it can't receive the result
        # anyway.
        save = 'return_url' in group_env
        if save:
            self.database.update(group_env['group_id'], {
                'id': group_env['group_id'],
                'env': group_env,
                'status': 'to_judge',
                'timestamp': time.time(),
                'retry_cnt': 0,
            })
        ret = yield self._addGroup(group_env)
        defer.returnValue(ret)

    def returnToSio(self, x, url, orig_env=None, tid=None, count=0):
        if isinstance(x, Failure):
            assert orig_env
            env = orig_env
            log.failure('Returning with error', x, LogLevel.warn)
        else:
            env = x

        if not tid:
            tid = env['group_id']

        bodygen, hdr = encode.multipart_encode({
                        'data': json.dumps(env)})
        body = ''.join(bodygen)

        headers = Headers({'User-Agent': ['sioworkersd']})
        for k, v in hdr.iteritems():
            headers.addRawHeader(k, v)

        def do_return():
            # This looks a bit too complicated for just POSTing a string,
            # but there seems to be no other way. Blame Twisted.

            # agent.request() will add content-length based on length
            # from FileBodyProducer. If we have another in headers,
            # there will be a duplicate, so remove it.
            headers.removeHeader('content-length')

            producer = client.FileBodyProducer(StringIO(body))
            d = self.agent.request('POST', url.encode('utf-8'),
                    headers, producer)

            @defer.inlineCallbacks
            def _response(r):
                if r.code != 200:
                    log.error('return error: server responded with status" \
                            "code {r.code}, response body follows...', r)
                    bodyD = yield client.readBody(r)
                    log.debug(bodyD)
                    raise RuntimeError('Failed to return task')
            d.addCallback(_response)
            return d
        ret = do_return()

        def _updateCount(x, n):
            self.database.update(tid, {'retry_cnt': n}, sync=False)
            # No db sync here, because we are allowing more attempts
            # of retrying returning job result for better performance.
            # It should be synced soon with other task
            # or `self.database` itself.
            return x  # Transparent callback

        def retry(err, retry_cnt):
            if retry_cnt >= MAX_RETRIES_OF_RESULT_RETURNING:
                log.error('Failed to return {tid} {count} times, giving up.',
                          tid=tid, count=retry_cnt)
                return
            log.warn('Returning {tid} to url {url} failed, retrying[{n}]...',
                     tid=tid, url=url, n=retry_cnt)
            log.failure('error was:', err, LogLevel.info)
            d = deferLater(reactor,
                           RETRY_DELAY_OF_RESULT_RETURNING[retry_cnt],
                           do_return)
            d.addBoth(_updateCount, n=retry_cnt)
            d.addErrback(retry, retry_cnt + 1)
            return d
        ret.addErrback(retry, retry_cnt=count)
        ret.addBoth(self._returnDone, tid=tid)
        return ret

    def _returnDone(self, _, tid):
        self.database.delete(str(tid), sync=False)
        # No db sync here, because we are allowing some jobs to be done
        # multiple times in case of server failure for better performance.
        # It should be synced soon with other task
        # or `self.database` itself.

    def _isTaskValid(self, task_env):
        """Checks if task should be accepted by sioworkersd.

        Right now the only reason for the task to be rejected is requiring
        more RAM than the global limit (2 GiB by default, configurable via
        command-line options).

        Returns a pair (bool, error: string?).
        """
        required_ram_mb = get_required_ram_for_job(task_env)
        if required_ram_mb > self.max_task_ram_mb:
            error = ('One of the tasks requires %d MiB of RAM, '
                    'exceeding the limit of %d MiB'
                    % (required_ram_mb, self.max_task_ram_mb))
            return False, error

        return True, None
