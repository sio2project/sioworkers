from __future__ import absolute_import
from twisted.trial import unittest
from twisted.test import proto_helpers
from twisted.internet import protocol, reactor
import json

from sio.protocol import rpc


class TestClient(rpc.WorkerRPC):
    def __init__(self):
        rpc.WorkerRPC.__init__(self, server=False)

    def doSomething(self, x):
        return self.call('foo', x)


class TestClientFactory(protocol.Factory):
    protocol = TestClient


class TestServer(rpc.WorkerRPC):
    def __init__(self):
        rpc.WorkerRPC.__init__(self, server=True)

    def cmd_mul3(self, x):
        return x * 3


class TestServerFactory(protocol.Factory):
    protocol = TestServer


def encode(x):
    x = json.dumps(x).encode('utf-8')
    return b''.join([str(len(x)).encode('utf-8'), b':', x, b','])


def decode(x):
    # This is a bit hacky, but we only care about the data part -
    # encoding netstrings is handled by Twisted and should work
    data = x.partition(b':')[2][:-1].decode('utf-8')
    return json.loads(data)


hello_msg = {'type': 'hello', 'data': {}}

hello_ack_msg = {'type': 'hello_ack'}


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        factory = TestServerFactory()
        self.proto = factory.buildProtocol(('127.0.0.1', 0))
        self.tr = proto_helpers.StringTransport()
        self.proto.makeConnection(self.tr)

    def _hello(self):
        self.proto.dataReceived(encode(hello_msg))
        self.assertEqual(decode(self.tr.value()), hello_ack_msg)
        self.assertEqual(self.proto.state, rpc.State.established)

    def test_server_hello(self):
        self._hello()

    def test_server_mul3(self):
        self._hello()
        self.tr.clear()
        self.proto.dataReceived(
            encode({'type': 'call', 'method': 'mul3', 'args': [5], 'id': 0})
        )
        ret = decode(self.tr.value())
        self.assertEqual(ret['result'], 15)


class ClientTestCase(unittest.TestCase):
    def setUp(self):
        factory = TestClientFactory()
        self.proto = factory.buildProtocol(('127.0.0.1', 0))
        self.tr = proto_helpers.StringTransport()
        self.proto.makeConnection(self.tr)

    def _hello(self):
        self.assertEqual(decode(self.tr.value()), hello_msg)
        self.assertEqual(self.proto.state, rpc.State.sent_hello)
        self.proto.dataReceived(encode(hello_ack_msg))
        self.assertEqual(self.proto.state, rpc.State.established)

    def test_client_hello(self):
        self._hello()

    def test_client_foo(self):
        self._hello()
        self.tr.clear()
        d = self.proto.doSomething(5)
        req = decode(self.tr.value())
        resp = encode({'type': 'result', 'id': req['id'], 'result': 'bar'})
        self.proto.dataReceived(resp)
        d.addCallback(self.assertEqual, 'bar')
        return d

    def test_client_timeout(self):
        self._hello()
        self.tr.clear()
        d = self.proto.call('foobar', timeout=0.5)
        d = self.assertFailure(d, rpc.TimeoutError)
        d.addCallback(lambda _: self.assertDictEqual(self.proto.pendingCalls, {}))
        return d


class IntegrationTestCase(unittest.TestCase):
    def setUp(self):
        factory = TestServerFactory()
        self.port = reactor.listenTCP(0, factory, interface='127.0.0.1')
        self.addCleanup(self.port.stopListening)

    def test_remote_call(self):
        creator = protocol.ClientCreator(reactor, TestClient)

        def cb(client):
            self.addCleanup(client.transport.loseConnection)
            d = client.call('mul3', 11)
            d.addCallback(self.assertEqual, 33)
            return d

        return creator.connectTCP('127.0.0.1', self.port.getHost().port).addCallback(cb)

    def test_nomethod(self):
        creator = protocol.ClientCreator(reactor, TestClient)

        def cb(client):
            self.addCleanup(client.transport.loseConnection)
            d = client.call('asdf')
            return self.assertFailure(d, rpc.RemoteError)

        return creator.connectTCP('127.0.0.1', self.port.getHost().port).addCallback(cb)
