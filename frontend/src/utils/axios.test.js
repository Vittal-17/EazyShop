jest.mock('axios', () => jest.requireActual('../../node_modules/axios/dist/browser/axios.cjs'));
import axios from 'axios';
import { createBrowserClient } from './axios';

const deferred = () => {
  let resolve;
  const promise = new Promise((ok) => { resolve = ok; });
  return { promise, resolve };
};
const response = (config, data = {}, status = 200) => ({ config, data, status, statusText: '', headers: {} });
const failure = (config, status, data = {}) => Object.assign(new Error('Fixture failure'), {
  config, response: response(config, data, status),
});
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
let client, adapter, handle;
beforeEach(() => {
  localStorage.clear();
  handle = async (config) => response(config, config.url === '/api/csrf/' ? { csrfToken: 'masked' } : {});
  adapter = jest.fn((config) => handle(config));
  axios.defaults.adapter = adapter;
  client = createBrowserClient('https://api.example.invalid');
});

it('bootstraps once before concurrent mutations and sends credentials/header without storage tokens', async () => {
  localStorage.setItem('access_token', 'legacy-credential');
  const gate = deferred();
  handle = async (config) => config.url === '/api/csrf/' ? gate.promise.then(() => response(config, { csrfToken: 'masked' })) : response(config);
  const writes = [client.post('/api/cart-items/', {}), client.patch('/api/users/1/', {}), client.delete('/api/addresses/1/')];
  await tick();
  expect(adapter.mock.calls.map(([config]) => config.url)).toEqual(['/api/csrf/']);
  gate.resolve();
  await Promise.all(writes);
  for (const [config] of adapter.mock.calls.slice(1)) {
    expect(config.withCredentials).toBe(true);
    expect(config.headers.get('X-CSRFToken')).toBe('masked');
    expect(config.headers.get('Authorization')).toBeUndefined();
    expect(config.xsrfCookieName).toBeNull();
    expect(config.timeout).toBe(30000);
  }
});

it('fails closed on bootstrap failure and permits recovery', async () => {
  handle = async () => { throw new Error('offline'); };
  await expect(client.post('/api/cart-items/', {})).rejects.toThrow('offline');
  expect(adapter).toHaveBeenCalledTimes(1);
  handle = async (config) => response(config, { csrfToken: 'recovered' });
  await expect(client.post('/api/cart-items/', {})).resolves.toBeDefined();
});

it('rejects external URLs before sending credentials', async () => {
  await expect(client.post('https://evil.example.invalid/collect', {})).rejects.toThrow('another origin');
  expect(adapter).not.toHaveBeenCalled();
});

it('shares a refresh across duplicate 401s and retries each request once', async () => {
  const gate = deferred();
  let rotated = false;
  handle = async (config) => {
    if (config.url === '/api/csrf/') return response(config, { csrfToken: 'masked' });
    if (config.url === '/api/token/refresh/') {
      expect(config.headers.get('X-CSRFToken')).toBe('masked');
      expect(JSON.parse(config.data)).toEqual({});
      await gate.promise; rotated = true;
      return response(config, { csrfToken: 'masked' });
    }
    if (!rotated) throw failure(config, 401);
    return response(config);
  };
  const requests = [client.get('/api/users/1/'), client.post('/api/cart-items/', {})];
  await tick(); gate.resolve(); await Promise.all(requests);
  expect(adapter.mock.calls.filter(([c]) => c.url === '/api/token/refresh/')).toHaveLength(1);
  expect(adapter.mock.calls.filter(([c]) => c._retry && c._authGeneration === 1)).toHaveLength(2);
  expect(localStorage.getItem('access_token')).toBeNull();
  expect(localStorage.getItem('refresh_token')).toBeNull();
});

it('does not rotate again for a late 401 from the previous generation', async () => {
  const late = deferred();
  handle = async (config) => {
    if (config.url === '/api/csrf/') return response(config, { csrfToken: 'masked' });
    if (config.url === '/api/token/refresh/' || config._retry) return response(config);
    if (config.url === '/api/late/') await late.promise;
    throw failure(config, 401);
  };
  const pending = client.get('/api/late/');
  await client.get('/api/early/'); late.resolve(); await pending;
  expect(adapter.mock.calls.filter(([c]) => c.url === '/api/token/refresh/')).toHaveLength(1);
});

it('rejects every waiting promise on expired refresh and reports expiry once', async () => {
  const expired = jest.fn(); client.setSessionExpiredHandler(expired);
  handle = async (config) => {
    if (config.url === '/api/csrf/') return response(config, { csrfToken: 'masked' });
    if (config.url === '/api/token/refresh/') await tick();
    throw failure(config, 401);
  };
  const results = await Promise.allSettled([client.get('/api/users/1/'), client.get('/api/orders/')]);
  expect(results.map((r) => r.status)).toEqual(['rejected', 'rejected']);
  expect(expired).toHaveBeenCalledTimes(1);
  expect(adapter.mock.calls.filter(([c]) => c.url === '/api/token/refresh/')).toHaveLength(1);
});

it('preserves session on refresh network failure and permits retry', async () => {
  const expired = jest.fn(); client.setSessionExpiredHandler(expired);
  let offline = true;
  handle = async (config) => {
    if (config.url === '/api/csrf/') return response(config, { csrfToken: 'masked' });
    if (config.url === '/api/token/refresh/') {
      if (offline) throw Object.assign(new Error('offline'), { config });
      return response(config);
    }
    if (!config._retry) throw failure(config, 401);
    return response(config);
  };
  await expect(client.get('/api/users/1/')).rejects.toThrow('offline');
  expect(expired).not.toHaveBeenCalled(); offline = false;
  await expect(client.get('/api/users/1/')).resolves.toBeDefined();
});

it('does not recursively refresh failed retries or login failures', async () => {
  handle = async (config) => {
    if (config.url === '/api/csrf/') return response(config, { csrfToken: 'masked' });
    if (config.url === '/api/token/refresh/') return response(config);
    throw failure(config, 401);
  };
  await expect(client.post('/api/token/', {})).rejects.toBeDefined();
  expect(adapter.mock.calls.filter(([c]) => c.url === '/api/token/refresh/')).toHaveLength(0);
  await expect(client.get('/api/users/1/')).rejects.toBeDefined();
  expect(adapter.mock.calls.filter(([c]) => c.url === '/api/token/refresh/')).toHaveLength(1);
});

it('uses login-rotated CSRF and recovers once after another tab rotates it', async () => {
  let csrfNumber = 0;
  handle = async (config) => {
    if (config.url === '/api/csrf/') return response(config, { csrfToken: `bootstrap-${++csrfNumber}` });
    if (config.url === '/api/token/') return response(config, { csrfToken: 'login-rotated' });
    if (!config._csrfRetry) {
      expect(config.headers.get('X-CSRFToken')).toBe('login-rotated');
      throw failure(config, 403, { code: 'csrf_failed' });
    }
    expect(config.headers.get('X-CSRFToken')).toBe('bootstrap-2');
    return response(config);
  };
  await client.post('/api/token/', {}); await client.post('/api/cart-items/', {});
  expect(csrfNumber).toBe(2);
});

it('propagates logout network failure without pretending the session ended', async () => {
  handle = async (config) => {
    if (config.url === '/api/csrf/') return response(config, { csrfToken: 'masked' });
    if (config.url === '/api/logout/') throw Object.assign(new Error('offline'), { config });
    return response(config);
  };
  await expect(client.logout()).rejects.toThrow('offline');
  await expect(client.get('/api/users/1/')).resolves.toBeDefined();
});

it('waits for refresh before logout and does not retry the protected request afterward', async () => {
  const gate = deferred();
  handle = async (config) => {
    if (config.url === '/api/csrf/') return response(config, { csrfToken: 'masked' });
    if (config.url === '/api/token/refresh/') { await gate.promise; return response(config); }
    if (config.url === '/api/logout/') return response(config);
    throw failure(config, 401);
  };
  const request = client.get('/api/users/1/').catch((error) => error);
  await tick(); const logout = client.logout(); await tick();
  expect(adapter.mock.calls.some(([c]) => c.url === '/api/logout/')).toBe(false);
  gate.resolve(); await logout;
  expect(await request).toBeInstanceOf(Error);
  expect(adapter.mock.calls.filter(([c]) => c.url === '/api/users/1/')).toHaveLength(1);
});
