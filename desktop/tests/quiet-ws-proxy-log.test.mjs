import assert from 'node:assert/strict';
import test from 'node:test';

import {
  quietWsProxySocketNote,
  shouldQuietWsProxySocketError,
} from '../scripts/quiet-ws-proxy-log.mjs';

test('仅压有 code 的 ws proxy socket 已关闭连接日志', () => {
  assert.equal(
    shouldQuietWsProxySocketError('ws proxy socket error:\nstack', { code: 'ECONNABORTED' }),
    true,
  );
  assert.equal(
    shouldQuietWsProxySocketError('ws proxy socket error:\nstack', { code: 'EPIPE' }),
    true,
  );
  assert.equal(
    shouldQuietWsProxySocketError('ws proxy socket error:\nstack', { code: 'ECONNRESET' }),
    true,
  );
});

test('真实连接失败与其它代理错误保留', () => {
  assert.equal(
    shouldQuietWsProxySocketError('ws proxy error:\nstack', { code: 'ECONNREFUSED' }),
    false,
  );
  assert.equal(
    shouldQuietWsProxySocketError('ws proxy socket error:\nstack', { code: 'ECONNREFUSED' }),
    false,
  );
  assert.equal(
    shouldQuietWsProxySocketError('ws proxy socket error:\nstack', null),
    false,
  );
  assert.equal(
    shouldQuietWsProxySocketError('http proxy error: boom', { code: 'ECONNABORTED' }),
    false,
  );
});

test('窄化说明含错误码', () => {
  assert.match(
    quietWsProxySocketNote('ws proxy socket error', { code: 'ECONNABORTED' }),
    /ECONNABORTED/,
  );
});
