import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createSidecarWsSession,
  RECONNECT_BASE_MS,
  RECONNECT_MAX_MS,
} from '../renderer/src/sidecarWsSession.mjs';

function mockClock() {
  let now = 0;
  let nextId = 1;
  const timers = new Map();
  return {
    setTimeout(fn, ms) {
      const id = nextId++;
      timers.set(id, { due: now + ms, fn });
      return id;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
    flush(ms) {
      const target = now + ms;
      while (true) {
        const next = [...timers.entries()]
          .filter(([, timer]) => timer.due <= target)
          .sort((a, b) => a[1].due - b[1].due)[0];
        if (!next) break;
        const [id, timer] = next;
        timers.delete(id);
        now = timer.due;
        timer.fn();
      }
      now = target;
    },
    pending() {
      return timers.size;
    },
  };
}

function mockWebSocketFactory() {
  const sockets = [];
  function createSocket() {
    const socket = {
      readyState: 0,
      closeCalls: 0,
      onopen: null,
      onmessage: null,
      onclose: null,
      onerror: null,
      close() {
        this.closeCalls += 1;
        this.readyState = 3;
        this.onclose?.();
      },
      open() {
        this.readyState = 1;
        this.onopen?.();
      },
    };
    sockets.push(socket);
    return socket;
  }
  return { createSocket, sockets };
}

test('StrictMode 首次 cleanup 清掉建连计时器，避免关闭 CONNECTING 连接', () => {
  const clock = mockClock();
  const { createSocket, sockets } = mockWebSocketFactory();
  const statusesA = [];
  const statusesB = [];
  const sessionA = createSidecarWsSession({
    url: 'ws://test/ws', createSocket, clock, onStatus: (s) => statusesA.push(s),
  });
  assert.equal(sockets.length, 0);
  assert.equal(clock.pending(), 1);
  sessionA.dispose();
  assert.equal(clock.pending(), 0);
  assert.equal(sessionA.getSocket(), null);
  assert.equal(sessionA.isDisposed(), true);

  const sessionB = createSidecarWsSession({
    url: 'ws://test/ws', createSocket, clock, onStatus: (s) => statusesB.push(s),
  });
  clock.flush(0);
  assert.equal(sockets.length, 1);
  assert.equal(sockets[0].closeCalls, 0);
  assert.equal(sessionB.getSocket(), sockets[0]);
  sockets[0].open();
  assert.deepEqual(statusesA, []);
  assert.deepEqual(statusesB, ['connecting', 'open']);
  sessionB.dispose();
});

test('dispose 摘掉消息回调，已捕获的晚到事件也不得派发', () => {
  const clock = mockClock();
  const { createSocket, sockets } = mockWebSocketFactory();
  const events = [];
  const jobs = [];
  const statuses = [];
  const session = createSidecarWsSession({
    url: 'ws://test/ws', createSocket, clock,
    onEvent: (m) => events.push(m), onJob: (m) => jobs.push(m), onStatus: (s) => statuses.push(s),
  });
  clock.flush(0);
  const socket = sockets[0];
  socket.open();
  const lateMessage = socket.onmessage;
  const lateOpen = socket.onopen;
  const lateClose = socket.onclose;
  const lateError = socket.onerror;
  session.dispose();
  session.dispose();
  for (const handler of ['onopen', 'onmessage', 'onclose', 'onerror']) assert.equal(socket[handler], null);
  lateMessage({ data: JSON.stringify({ type: 'event', name: 'late' }) });
  lateMessage({ data: JSON.stringify({ type: 'job', id: 'late' }) });
  lateOpen();
  lateClose();
  lateError();
  assert.equal(socket.closeCalls, 1);
  assert.equal(events.length, 0);
  assert.equal(jobs.length, 0);
  assert.deepEqual(statuses, ['connecting', 'open']);
  assert.equal(clock.pending(), 0);
});

test('真实断线逐级退避到10秒，成功连接后恢复500毫秒', () => {
  const clock = mockClock();
  const { createSocket, sockets } = mockWebSocketFactory();
  const statuses = [];
  const session = createSidecarWsSession({
    url: 'ws://test/ws', createSocket, clock, onStatus: (s) => statuses.push(s),
  });
  clock.flush(0);
  sockets[0].open();
  for (let attempt = 0; attempt < 7; attempt += 1) {
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);
    const count = sockets.length;
    sockets.at(-1).close();
    assert.equal(statuses.at(-1), 'closed');
    assert.equal(clock.pending(), 1);
    clock.flush(delay - 1);
    assert.equal(sockets.length, count);
    clock.flush(1);
    assert.equal(sockets.length, count + 1);
  }
  sockets.at(-1).open();
  const count = sockets.length;
  sockets.at(-1).close();
  clock.flush(RECONNECT_BASE_MS - 1);
  assert.equal(sockets.length, count);
  clock.flush(1);
  assert.equal(sockets.length, count + 1);
  session.dispose();
});

test('旧 socket 重复关闭回调只安排一次重连，不能污染新 socket', () => {
  const clock = mockClock();
  const { createSocket, sockets } = mockWebSocketFactory();
  const statuses = [];
  const session = createSidecarWsSession({
    url: 'ws://test/ws', createSocket, clock, onStatus: (s) => statuses.push(s),
  });
  clock.flush(0);
  const old = sockets[0];
  const lateClose = old.onclose;
  old.close();
  lateClose();
  assert.equal(clock.pending(), 1);
  assert.equal(statuses.filter((s) => s === 'closed').length, 1);
  clock.flush(RECONNECT_BASE_MS);
  assert.equal(sockets.length, 2);
  const current = sockets[1];
  lateClose();
  assert.equal(session.getSocket(), current);
  assert.equal(clock.pending(), 0);
  clock.flush(RECONNECT_MAX_MS);
  assert.equal(sockets.length, 2);
  session.dispose();
});

test('dispose 取消待重连计时器', () => {
  const clock = mockClock();
  const { createSocket, sockets } = mockWebSocketFactory();
  const session = createSidecarWsSession({ url: 'ws://test/ws', createSocket, clock });
  clock.flush(0);
  sockets[0].close();
  assert.equal(clock.pending(), 1);
  session.dispose();
  assert.equal(clock.pending(), 0);
  clock.flush(RECONNECT_MAX_MS);
  assert.equal(sockets.length, 1);
});

test('存活连接的真实 error 仍关闭连接并按退避重连', () => {
  const clock = mockClock();
  const { createSocket, sockets } = mockWebSocketFactory();
  const session = createSidecarWsSession({ url: 'ws://test/ws', createSocket, clock });
  clock.flush(0);
  sockets[0].onerror();
  assert.equal(sockets[0].closeCalls, 1);
  assert.equal(clock.pending(), 1);
  clock.flush(RECONNECT_BASE_MS);
  assert.equal(sockets.length, 2);
  session.dispose();
});

test('事件及任务分别派发，非法JSON和未知消息不派发', () => {
  const clock = mockClock();
  const { createSocket, sockets } = mockWebSocketFactory();
  const events = [];
  const jobs = [];
  const session = createSidecarWsSession({
    url: 'ws://test/ws', createSocket, clock,
    onEvent: (m) => events.push(m), onJob: (m) => jobs.push(m),
  });
  clock.flush(0);
  const message = sockets[0].onmessage;
  const event = { type: 'event', name: 'progress', data: { done: 2 } };
  const job = { type: 'job', id: 'running' };
  message({ data: JSON.stringify(event) });
  message({ data: JSON.stringify(job) });
  message({ data: '{bad' });
  message({ data: 'null' });
  message({ data: JSON.stringify({ type: 'unknown' }) });
  assert.deepEqual(events, [event]);
  assert.deepEqual(jobs, [job]);
  session.dispose();
});
