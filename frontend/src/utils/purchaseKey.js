// A retry identifier, never a credential. Keep it across refresh/unknown outcomes.
const storageKey = (purpose, userId) => `eazyshop:purchase:${purpose}:${userId}`;

export function purchaseKey(purpose, userId) {
  const name = storageKey(purpose, userId);
  let key = sessionStorage.getItem(name);
  if (!key) {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    key = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
    sessionStorage.setItem(name, key);
  }
  return key;
}

export function clearPurchaseKey(purpose, userId, expectedKey) {
  const name = storageKey(purpose, userId);
  if (expectedKey === undefined || sessionStorage.getItem(name) === expectedKey) {
    sessionStorage.removeItem(name);
  }
}
