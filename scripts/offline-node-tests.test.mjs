import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import './offline-node-tests.mjs';

test('external HTTP and sockets are rejected before sending any request', () => {
  for (const host of ['203.0.113.9', '192.168.1.50', '127.example.com']) {
    assert.throws(() => fetch(`http://${host}/`), /External network disabled/);
    const socket = new net.Socket();
    try {
      assert.throws(
        () => socket.connect({ host, port: 443 }),
        /External network disabled/,
      );
    } finally {
      socket.destroy();
    }
  }
});

test('loopback HTTP services remain usable for integration tests', async () => {
  const server = http.createServer((req, res) => res.end('local test'));
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    const response = await fetch(`http://127.0.0.1:${server.address().port}/`);
    assert.equal(await response.text(), 'local test');
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
});
