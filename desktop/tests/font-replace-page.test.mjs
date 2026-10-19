import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync(new URL('../renderer/src/pages/FontReplacePage.tsx', import.meta.url), 'utf8');

test('font scan is only started by the explicit rescan action', () => {
  const scanRequests = page.match(/suite\.submit\('\/api\/font-tools\/scan'/g) ?? [];
  assert.equal(scanRequests.length, 1);
  assert.match(page, /function rescan\(\) \{[\s\S]*?suite\.submit\('\/api\/font-tools\/scan'/);
});
