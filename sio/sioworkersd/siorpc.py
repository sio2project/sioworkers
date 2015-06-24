from twisted.web.xmlrpc import XMLRPC
from twisted.web import server
from uuid import uuid4
from sio.sioworkersd.quirks import apply_quirks
from twisted.internet import defer
from twisted.logger import Logger

log = Logger()


# It seems that every Twisted JSONRPC library sucks or is missing features,
# so we have to settle for XMLRPC.
class SIORPC(XMLRPC):
    addSlash = True

    def __init__(self, workerm, taskm):
        XMLRPC.__init__(self, allowNone=True)
        self.workerm = workerm
        self.taskm = taskm

    def xmlrpc_get_workers(self):
        ret = []
        for k, v in self.workerm.getWorkers().iteritems():
            ret.append({'name': k,
                'info': v.info,
                'tags': list(v.tags),
                'tasks': list(v.tasks),
                'exclusive': v.exclusive})
        return ret

    @defer.inlineCallbacks
    def xmlrpc_add_tag(self, workers, tag):
        for i in workers:
            yield self.workerm.addWorkerTag(i, tag)

    @defer.inlineCallbacks
    def xmlrpc_del_tag(self, workers, tag):
        for i in workers:
            yield self.workerm.removeWorkerTag(i, tag)

    def xmlrpc_list_tags(self):
        ret = set()
        for i in self.workerm.getWorkers().itervalues():
            ret.update(i.tags)
        return list(ret)

    def xmlrpc_get_queue(self):
        return self.taskm.getQueue()

    def xmlrpc_run(self, task):
        task_id = uuid4().urn
        task['task_id'] = task_id
        apply_quirks(task)
        d = self.taskm.addTask(task)
        d.addBoth(self.taskm.return_to_sio, url=task['return_url'],
                orig_env=task)
        return task_id

    def _sync_wrap(self, err, orig_env):
        orig_env['error'] = {'message': err.getErrorMessage(),
                             'traceback': err.getTraceback()}
        log.failure('Synchronous task failed', err)
        err.printTraceback()
        return orig_env

    def xmlrpc_sync_run(self, task):
        task_id = uuid4().urn
        task['task_id'] = task_id
        apply_quirks(task)
        d = self.taskm.addTask(task)
        d.addErrback(self._sync_wrap, orig_env=task)
        return d

    def _prepare_group(self, env):
        tasks = env['workers_jobs']
        group_id = 'GROUP_' + uuid4().urn
        env['group_id'] = group_id
        for task in tasks.itervalues():
            apply_quirks(task)
            task['group_id'] = group_id
            task['task_id'] = uuid4().urn

    def xmlrpc_run_group(self, env):
        self._prepare_group(env)
        d = self.taskm.addTaskGroup(env)
        d.addBoth(self.taskm.return_to_sio, url=env['return_url'],
                orig_env=env)
        return env['group_id']

    def xmlrpc_sync_run_group(self, env):
        self._prepare_group(env)
        d = self.taskm.addTaskGroup(env)
        d.addErrback(self._sync_wrap, orig_env=env)
        return d


def makeSite(workerm, taskm):
    p = SIORPC(workerm, taskm)
    return server.Site(p)
