import { purchaseKey, clearPurchaseKey } from './purchaseKey';

beforeEach(() => sessionStorage.clear());

test('unknown outcomes and refreshes reuse a purpose and user scoped key', () => {
  const key = purchaseKey('merchandise', 1);
  expect(purchaseKey('merchandise', 1)).toBe(key);
  expect(purchaseKey('gift_card', 1)).not.toBe(key);
  expect(purchaseKey('merchandise', 2)).not.toBe(key);
  expect(key).toMatch(/^[a-f0-9]{32}$/);
});

test('only confirmed completion or cancellation clears the retry identity', () => {
  const key = purchaseKey('merchandise', 1);
  clearPurchaseKey('gift_card', 1);
  expect(purchaseKey('merchandise', 1)).toBe(key);
  clearPurchaseKey('merchandise', 1);
  expect(purchaseKey('merchandise', 1)).not.toBe(key);
});

test('recovering an older completed gift cannot clear a newer unresolved request', () => {
  const current = purchaseKey('gift_card', 1);
  clearPurchaseKey('gift_card', 1, 'older-request');
  expect(purchaseKey('gift_card', 1)).toBe(current);
  clearPurchaseKey('gift_card', 1, current);
  expect(purchaseKey('gift_card', 1)).not.toBe(current);
});
