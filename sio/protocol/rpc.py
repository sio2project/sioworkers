from twisted.protocols.basic import NetstringReceiver
from twisted.internet import defer, reactor
from twisted.python import log

import json
from enum import Enum

State = Enum('State', 'connected sent_hello established')


class TimeoutError(Exception):
    pass


class ProtocolError(Exception):
    pass


class RemoteError(Exception):
    def __init__(self, err, tb=None):
        super(RemoteError, self).__init__(err)
        self.traceback = tb


class NoSuchMethodError(RemoteError):
    def __init__(self, err=None):
        super(NoSuchMethodError, self).__init__(err)

# This function doesn't do much right now, but it can easily be extended
# for passing any exceptions with arbitrary parameters (JSON serializable)
def makeRemoteException(msg):
    """Make an Exception instance from message dict.
    This function does *not* throw, just returns the object."""
    if msg['kind'] == 'method_not_found':
        return NoSuchMethodError()
    else:
        return RemoteError('%s: %s' % (msg['kind'], msg['data']),
                msg.get('traceback'))


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
            print 'sent hello'

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
                                    kind='method_not_found', id=msg['id'])
                    return
                d = defer.maybeDeferred(f, *msg['args'])
                d.addCallback(self._reply, request=msg['id'])
                d.addErrback(self._replyError, request=msg['id'])
            elif msg['type'] == 'error':
                d = self.pendingCalls.get(msg['id'])
                if d is None:
                    raise ProtocolError("got error for unknown call")
                del self.pendingCalls[msg['id']]
                exc = makeRemoteException(msg)
                d[0].errback(exc)
                d[1].cancel()
        elif self.state == State.connected:
            if not self.isServer:
                raise ProtocolError("received %s before client hello was sent"
                                    % str(msg))
            else:
                if msg['type'] == 'hello':
                    print 'got hello'
                    self.clientInfo = msg['data']
                    self.sendMsg('hello_ack')
                    self.state = State.established
                    self.ready.callback(None)
                else:
                    raise ProtocolError("expected client hello, got %s"
                                        % str(msg))
        elif self.state == State.sent_hello:
            if msg['type'] == 'hello_ack':
                print 'got hello_ack'
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
                msg = json.loads(string)
            except ValueError as e:
                log.err(e, "Received message with invalid JSON. Terminating.")
                raise
            self._processMessage(msg)
        except ProtocolError as e:
            log.err(e, "Fatal protocol error. Terminating.")
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

    def _timeout(self, d):
        d.errback(TimeoutError())

    def sendMsg(self, msg_type, **kwargs):
        kwargs['type'] = msg_type
        self.sendString(json.dumps(kwargs))

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
        timer = reactor.callLater(timeout, self._timeout, d)

        def cb(ignore):
            self.pendingCalls[self.requestID] = (d, timer)
            s = json.dumps({'type': 'call', 'id': self.requestID,
                'method': cmd, 'args': args})
            self.requestID += 1
            self.sendString(s)
        if self.state != State.established:
            # wait for connection
            self.ready.addCallback(cb)
        else:
            cb(None)
        return d
