import assert from 'node:assert/strict';
import test from 'node:test';

import {
  gameModOwnerIdentity,
  gameModStatusTone,
} from '../renderer/src/gameModView.mjs';

test('owner_identity helper only accepts string arrays', () => {
  assert.deepEqual(gameModOwnerIdentity({ owner_identity: ['a', 'b'] }), ['a', 'b']);
  assert.equal(gameModOwnerIdentity({ owner_identity: 'x' }), undefined);
});

test('status tone marks partial/cancelled as warning, not success', () => {
  assert.equal(
    gameModStatusTone({ job: { status: 'cancelled' }, result: { written: true, partial: true, success: false } }),
    'warning',
  );
  assert.equal(
    gameModStatusTone({ job: { status: 'done' }, result: { success: true } }),
    'success',
  );
});
