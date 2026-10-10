/**
 * Run a child command beside a loopback-only PostgreSQL WASM database.
 *
 * npm ci --prefix scripts/evidence_review_benchmark/pglite --ignore-scripts
 * node scripts/evidence_review_benchmark/pglite/run-with-pglite.mjs \
 *   --data-dir /tmp/knowhere-pglite/benchmark-data -- .venv/bin/python ...
 *
 * This is a real PostgreSQL SQL/index engine, but has one backend multiplexed
 * across client connections. Use sequential benchmark episodes, not concurrent
 * transactions or production throughput measurements. No model configuration
 * or credential is inspected or logged by this launcher.
 */
import { spawn } from 'node:child_process';
import { createServer, connect } from 'node:net';
import { parseArgs } from 'node:util';

import { PGlite } from '@electric-sql/pglite';
import { pg_trgm } from '@electric-sql/pglite/contrib/pg_trgm';
import { uuid_ossp } from '@electric-sql/pglite/contrib/uuid_ossp';
import { PGLiteSocketServer } from '@electric-sql/pglite-socket';

const separator = process.argv.indexOf('--');
if (separator < 0 || separator === process.argv.length - 1) {
  console.error('Usage: run-with-pglite.mjs [--data-dir PATH] [--port PORT] -- COMMAND [ARG ...]');
  process.exit(2);
}
const { values } = parseArgs({
  args: process.argv.slice(2, separator),
  options: {
    'data-dir': { type: 'string', default: '/tmp/knowhere-pglite/benchmark-data' },
    port: { type: 'string', default: '0' },
  },
});
const port = Number(values.port);
if (!Number.isInteger(port) || port < 0 || port > 65535) {
  console.error('Port must be an integer between 0 and 65535.');
  process.exit(2);
}

const db = await PGlite.create({
  dataDir: values['data-dir'], extensions: { pg_trgm, uuid_ossp },
});
await db.exec('CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE EXTENSION IF NOT EXISTS "uuid-ossp";');
const server = new PGLiteSocketServer({
  db, host: '127.0.0.1', port: 0, maxConnections: 10,
});
await server.start();
const backendPort = Number(server.getServerConn().split(':').at(-1));
const sockets = new Set();

// pglite-socket 0.2.11 processes PostgreSQL Terminate without closing its TCP
// socket. asyncpg.close() waits for the server to close, so NullPool cleanup
// hangs. Forward all bytes unchanged and finish the connection only after a
// complete Terminate frame. This changes transport shutdown, never SQL/results.
// SSL/GSS negotiation requests precede the actual StartupMessage and must not
// switch the parser to tagged frames. asyncpg may negotiate even when an app's
// "disable" setting merely omits the ssl connection argument.
const frontend = createServer((client) => {
  const backend = connect({ host: '127.0.0.1', port: backendPort });
  sockets.add(client);
  sockets.add(backend);
  let startup = true;
  let buffered = Buffer.alloc(0);
  const close = () => {
    client.destroy();
    backend.destroy();
    sockets.delete(client);
    sockets.delete(backend);
  };
  client.on('error', close);
  backend.on('error', close);
  client.on('close', close);
  backend.on('close', close);
  backend.pipe(client);
  backend.on('drain', () => client.resume());
  client.on('data', (data) => {
    if (!backend.write(data)) client.pause();
    buffered = Buffer.concat([buffered, data]);
    while (buffered.length >= (startup ? 4 : 5)) {
      const length = buffered.readUInt32BE(startup ? 0 : 1) + (startup ? 0 : 1);
      if (length < (startup ? 8 : 5) || length > 64 * 1024 * 1024) {
        close();
        return;
      }
      if (buffered.length < length) return;
      const terminate = !startup && buffered[0] === 88 && length === 5;
      const negotiating = startup && length === 8
        && [80877103, 80877104].includes(buffered.readUInt32BE(4));
      buffered = buffered.subarray(length);
      if (!negotiating) startup = false;
      if (terminate) {
        backend.end();
        client.end();
        return;
      }
    }
  });
});
await new Promise((resolve, reject) => {
  frontend.once('error', reject);
  frontend.listen(port, '127.0.0.1', resolve);
});
const boundPort = frontend.address().port;
const databaseUrl = `postgresql+asyncpg://postgres@127.0.0.1:${boundPort}/postgres`;
console.log(JSON.stringify({
  status: 'ready', backend: 'PGlite', host: '127.0.0.1', port: boundPort,
  postgres_version: (await db.query('select version()')).rows[0].version,
  extensions: ['pg_trgm', 'uuid-ossp'],
}));

const [command, ...args] = process.argv.slice(separator + 1);
const child = spawn(command, args, {
  stdio: 'inherit',
  env: {
    ...process.env,
    DATABASE_URL: databaseUrl,
    MIGRATION_DATABASE_URL: databaseUrl.replace('+asyncpg', '+psycopg2'),
    DB_SSL_MODE: 'disable',
    DB_USE_NULL_POOL: 'true',
  },
});
let cleaning = false;
async function cleanup(code) {
  if (cleaning) return;
  cleaning = true;
  for (const socket of sockets) socket.destroy();
  await new Promise((resolve) => frontend.close(resolve));
  await server.stop();
  await db.close();
  process.exit(code);
}
child.once('exit', (code) => { void cleanup(code ?? 1); });
child.once('error', (error) => {
  console.error(JSON.stringify({ status: 'child_start_failed', error_type: error.code }));
  void cleanup(1);
});
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, () => { child.kill(signal); });
}
