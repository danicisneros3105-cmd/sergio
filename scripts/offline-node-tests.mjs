/** Preload with NODE_OPTIONS=--import=... to keep Node tests on loopback. */
import net from 'node:net';

function assertLocal(host) {
  host = host == null ? host : String(host).replace(/^\[|\]$/g, '');
  if (
    host == null ||
    host === 'localhost' ||
    host === '::1' ||
    host === '0.0.0.0' ||
    (net.isIP(host) === 4 && host.startsWith('127.'))
  )
    return;
  throw new Error('External network disabled in tests; mock the service');
}

const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  let options = args[0];
  if (Array.isArray(options)) options = options[0];
  if (options && typeof options === 'object') {
    if (!options.path) {
      if (typeof options.lookup === 'function') {
        const lookup = options.lookup;
        options.lookup = (host, opts, callback) =>
          lookup(host, opts, (error, address, family) => {
            if (error) return callback(error);
            try {
              for (const entry of Array.isArray(address)
                ? address
                : [{ address }]) {
                assertLocal(entry.address);
              }
              callback(null, address, family);
            } catch (failure) {
              callback(failure);
            }
          });
      } else assertLocal(options.host);
    }
  } else if (typeof options === 'number') {
    assertLocal(typeof args[1] === 'string' ? args[1] : undefined);
  } else if (typeof options === 'string' && !options.includes('/')) {
    // A numeric string is a TCP port; a file path denotes local IPC.
    if (/^\d+$/.test(options)) {
      assertLocal(typeof args[1] === 'string' ? args[1] : undefined);
    } else {
      assertLocal(options);
    }
  }
  return connect.apply(this, args);
};

const fetch = globalThis.fetch;
globalThis.fetch = function (input, ...args) {
  assertLocal(
    new URL(typeof input === 'string' ? input : (input.url ?? input)).hostname,
  );
  return fetch.call(this, input, ...args);
};
