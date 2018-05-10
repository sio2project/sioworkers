from __future__ import absolute_import
from twisted.protocols.basic import NetstringReceiver
from twisted.internet import defer, reactor
from twisted.logger import Logger
import six

log = Logger()

import json
from enum import Enum


State = Enum('State', 'connected sent_hello established')


class TimeoutError(Exception):
    pass


class ProtocolError(Exception):
    pass


class RemoteError(Exception):
    def __init__(self, err, tb=None, uid=None):
        if uid is not None:
            err = "received from " + uid + ("" if err is None else ": " + err)
        super(RemoteError, self).__init__(err)
        self.traceback = tb
        self.uid = uid


class NoSuchMethodError(RemoteError):
    def __init__(self, err=None, uid=None):
        super(NoSuchMethodError, self).__init__(err, uid=uid)

# This function doesn't do much right now, but it can easily be extended
# for passing any exceptions with arbitrary parameters (JSON serializable)
def makeRemoteException(msg, uid=None):
    """Make an Exception instance from message dict.
    This function does *not* throw, just returns the object."""
    err = '%s: %s' % (msg['kind'], msg['data'])
    if msg['kind'] == 'method_not_found':
        return NoSuchMethodError(err, uid=uid)
    else:
        return RemoteError(err=err, tb=msg.get('traceback'), uid=uid)


class WorkerRPC(NetstringReceiver):
    MAX_LENGTH = 2**20  # 1MB should be enough
    DEFAULT_TIMEOUT = 30

    def __init__(self, server=False, timeout=DEFAULT_TIMEOUT):
        self.requestID = 0
        # dictionary of pending call() requests,
        # pendingCalls[requestID] = (returned deferred, timeout deferred)
        self.pendingCalls = {}
        self.isServer = server
        self.state = None
        # Fired when state changes to established.
        self.ready = defer.Deferred()
        self.defaultTimeout = timeout
        self.clientInfo = {}

    def connectionMade(self):
        self.state = State.connected
        if not self.isServer:
            self.sendMsg('hello', data=self.getHelloData())
            self.state = State.sent_hello
            log.debug('sent hello')

    def connectionLost(self, reason):
        NetstringReceiver.connectionLost(self, reason)
        for (_, timer) in six.itervalues(self.pendingCalls):
            if not timer.called:
                timer.cancel()

    def _processMessage(self, msg):
        if self.state == State.established:
            if msg['type'] == 'result':
                d = self.pendingCalls.get(msg['id'])
                if d is None:
                    raise ProtocolError("got result for unknown call")
                del self.pendingCalls[msg['id']]
                d[0].callback(msg['result'])
                d[1].cancel()
            elif msg['type'] == 'call':
                try:
                    f = getattr(self, 'cmd_' + msg['method'])
                except AttributeError:
                    self.sendMsg('error',
                                    kind='method_not_found', id=msg['id'],
                                    data=msg['method'])
                    return
                d = defer.maybeDeferred(f, *msg['args'])
                d.addCallback(self._reply, request=msg['id'])
                d.addErrback(self._replyError, request=msg['id'])
            elif msg['type'] == 'error':
                d = self.pendingCalls.get(msg['id'])
                if d is None:
                    raise ProtocolError("got error for unknown call")
                del self.pendingCalls[msg['id']]
                exc = makeRemoteException(msg,
                        uid=getattr(self, 'uniqueID', None))
                d[0].errback(exc)
                d[1].cancel()
        elif self.state == State.connected:
            if not self.isServer:
                raise ProtocolError("received %s before client hello was sent"
                                    % str(msg))
            else:
                if msg['type'] == 'hello':
                    log.debug('got hello')
                    self.clientInfo = msg['data']
                    self.sendMsg('hello_ack')
                    self.state = State.established
                    self.ready.callback(None)
                else:
                    raise ProtocolError("expected client hello, got %s"
                                        % str(msg))
        elif self.state == State.sent_hello:
            if msg['type'] == 'hello_ack':
                log.debug('got hello_ack')
                self.state = State.established
                self.ready.callback(None)
            else:
                raise ProtocolError("expected hello_ack, got %s" % str(msg))

    def getHelloData(self):
        """Placeholder method, reimplement in derived class.
        Should return a dict."""
        return {}

    def stringReceived(self, string):
        try:
            try:
                msg = json.loads(string.decode())
            except ValueError:
                log.failure("Received message with invalid JSON. Terminating.")
                raise
            self._processMessage(msg)
        except ProtocolError:
            log.failure("Fatal protocol error. Terminating.")
            self.transport.loseConnection()
        except:
            self.transport.loseConnection()
            raise

    def _reply(self, value, request=None):
        self.sendMsg('result', id=request, result=value)

    def _replyError(self, err, request=None):
        self.sendMsg('error', id=request, kind='exception', data=repr(err),
                traceback=err.getTraceback())
        # Don't return here - we would get potentially useless
        # 'unhandled error' messages

    def _timeout(self, rid):
        d = self.pendingCalls[rid][0]
        del self.pendingCalls[rid]
        d.errback(TimeoutError())

    def sendMsg(self, msg_type, **kwargs):
        kwargs['type'] = msg_type
        self.sendString(json.dumps(kwargs).encode('utf-8'))

    def call(self, cmd, *args, **kwargs):
        """Call a remote function. Raises RemoteError if something goes wrong
        on the remote end and TimeoutError on timeout.
        Warning: remote tasks can *not* be cancelled and will keep executing
        even if connection is dropped. You should handle this manually.
        """
        if 'timeout' in kwargs:
            timeout = kwargs['timeout']
        else:
            timeout = self.defaultTimeout
        d = defer.Deferred()
        current_id = self.requestID
        self.requestID += 1
        timer = reactor.callLater(timeout, self._timeout, current_id)

        def cb(ignore):
            self.pendingCalls[current_id] = (d, timer)
            s = json.dumps({'type': 'call', 'id': current_id,
                'method': cmd, 'args': args})
            self.sendString(s.encode('utf-8'))
        if self.state != State.established:
            # wait for connection
            self.ready.addCallback(cb)
        else:
            cb(None)
        return d
