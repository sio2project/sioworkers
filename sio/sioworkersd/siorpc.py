import json
from functools import wraps
from twisted.web.xmlrpc import XMLRPC
from twisted.web import server
from uuid import uuid4
from twisted.logger import Logger

log = Logger()

def escape_arguments(func):
    def unpack(a):
        try:
            return json.loads(a)
        except (ValueError, TypeError):
            return a

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        return func(self,
                    *[unpack(a) for a in args],
                    **{k: unpack(v) for (k, v) in kwargs.iteritems()})
    return wrapper


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
                'tasks': list(v.tasks),
                'is_running_cpu_exec': v.is_running_cpu_exec})
        return ret

    def xmlrpc_get_queue(self):
        return self.taskm.getQueue()

    def xmlrpc_get_tasks(self):
        return self.taskm.getTasks()

    def _prepare_group(self, env):
        tasks = env['workers_jobs']
        group_id = 'GROUP_' + uuid4().urn
        env['group_id'] = group_id
        for task in tasks.itervalues():
            task['group_id'] = group_id
            task['task_id'] = uuid4().urn

    @escape_arguments
    def xmlrpc_run_group(self, env):
        self._prepare_group(env)
        d = self.taskm.addTaskGroup(env)
        d.addBoth(self.taskm.returnToSio, url=env['return_url'],
                orig_env=env)
        return env['group_id']

    @escape_arguments
    def xmlrpc_sync_run_group(self, env):
        self._prepare_group(env)
        return self.taskm.addTaskGroup(env)


def makeSite(workerm, taskm):
    p = SIORPC(workerm, taskm)
    return server.Site(p)
