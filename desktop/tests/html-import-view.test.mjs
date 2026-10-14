import assert from 'node:assert/strict';
import test from 'node:test';

import {
  htmlImportOwnerIdentity,
  htmlImportStatusTone,
} from '../renderer/src/htmlImportView.mjs';

test('owner_identity helper only accepts string arrays', () => {
  assert.deepEqual(htmlImportOwnerIdentity({ owner_identity: ['', ''] }), ['', '']);
  assert.equal(htmlImportOwnerIdentity({ owner_identity: [1] }), undefined);
  assert.equal(htmlImportOwnerIdentity(null), undefined);
});

test('status tone marks partial/cancelled as warning, not success', () => {
  assert.equal(
    htmlImportStatusTone({ job: { status: 'cancelled' }, result: { written: true, partial: true, success: false } }),
    'warning',
  );
  assert.equal(
    htmlImportStatusTone({ job: { status: 'done' }, result: { success: true, partial: false } }),
    'success',
  );
  assert.equal(
    htmlImportStatusTone({ job: { status: 'failed' }, result: { written: false } }),
    'error',
  );
});
