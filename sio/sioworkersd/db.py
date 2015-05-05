"""sioworkersd database API.
We use a simple sqlite ... TODO

Schema:
    config: Simple key-value store.
            required row: 'version' = DB_VERSION
    tasks: Saved task list. Groups are stored as a single row,
                tasks from a group are *not* added separately.
            id - 'task_id' or 'group_id' (see is_group) from env
            env - task/group environment as json
            is_group - true if this row describes a group
            time - time when task was received
    workers: TODO
    worker_tag: TODO
"""
from twisted.enterprise import adbapi
from twisted.internet import defer
from twisted.application import service


class DBWrapper(service.MultiService):
    """This class basically wraps a ConnectionPool, creating/migrating
    the database on start if required.
    Any services which use the database must have this service as a parent.
    Children will be started only after the connection is ready.
    """
    DB_VERSION = 1
    schema = ["CREATE TABLE config \
                    (key TEXT PRIMARY KEY, value TEXT NOT NULL);",
            "CREATE TABLE task \
                    (id TEXT PRIMARY KEY, \
                    env BLOB NOT NULL, \
                    is_group BOOLEAN NOT NULL DEFAULT 0, \
                    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP);",
            "CREATE TABLE return_task \
                    (id TEXT PRIMARY KEY, \
                    env BLOB NOT NULL,  \
                    count INTEGER NOT NULL DEFAULT 0);",
            "CREATE TABLE worker \
                    (name TEXT PRIMARY KEY);",
            "CREATE TABLE worker_tag \
                    (tag TEXT, worker TEXT, \
                    FOREIGN KEY(worker) REFERENCES worker(name));",
            "CREATE INDEX tag_idx ON worker_tag(tag);"]

    def __init__(self, path):
        service.MultiService.__init__(self)
        self.path = path
        self.pool = None

    def runQuery(self, *args, **kwargs):
        return self.pool.runQuery(*args, **kwargs)

    def runOperation(self, *args, **kwargs):
        return self.pool.runOperation(*args, **kwargs)

    @defer.inlineCallbacks
    def startService(self):
        # note: we do NOT call MultiSerivce.startService here, as it
        # starts children, which we want do do on our own
        service.Service.startService(self)
        yield self.openDB()
        print 'starting children'
        for srv in self:
            yield srv.startService()

    @defer.inlineCallbacks
    def makeDB(self):
        for i in self.schema:
            yield self.pool.runOperation(i)
        tables = yield self.pool.runQuery(
                "select name from sqlite_master where type = 'table'")
        print 'Created database version', self.DB_VERSION, 'tables', \
                tables
        yield self.pool.runQuery("insert into config values ('version', ?)",
                str(self.DB_VERSION))

    # if we ever need to change the db schema, we should migrate it here
    def migrate(self, fromVersion):
        raise RuntimeError('migration required but not implemented')

    @defer.inlineCallbacks
    def openDB(self):
        # check_same_thread=False is safe according to
        # https://twistedmatrix.com/trac/ticket/3629
        self.pool = adbapi.ConnectionPool('sqlite3', self.path,
                check_same_thread=False)
        print 'db open'
        tables = yield self.pool.runQuery(
                "select name from sqlite_master where type = 'table'")
        if 'config' not in [i[0] for i in tables]:
            yield self.makeDB()
        ver = yield self.pool.runQuery(
                "select value from config where key = 'version'")
        ver = ver[0][0]
        if int(ver) != self.DB_VERSION:
            yield self.migrate(int(ver))
