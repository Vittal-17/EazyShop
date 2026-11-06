import axios from 'axios';

const localHost = window.location.hostname === '127.0.0.1' ? '127.0.0.1' : 'localhost';
const API_URL = process.env.REACT_APP_API_URL || `http://${localHost}:8000`;
const unsafe = (method) => !['get', 'head', 'options'].includes((method || 'get').toLowerCase());
const authEndpoint = (url) => /\/api\/(token(?:\/refresh)?|logout|register|password-reset\/[^/]+)\/$/.test(url);

export function createBrowserClient(baseURL = API_URL) {
  const options = { baseURL, withCredentials: true, timeout: 30000, xsrfCookieName: null };
  const transport = axios.create(options);
  const client = axios.create(options);
  let csrfToken;
  let csrfPromise;
  let refreshPromise;
  let generation = 0;
  let sessionEnded = false;
  let loggingOut = false;
  let onSessionExpired = () => {};

  client.setSessionExpiredHandler = (handler) => {
    onSessionExpired = handler;
    return () => { onSessionExpired = () => {}; };
  };

  client.ensureCSRF = async (force = false) => {
    if (force) csrfToken = undefined;
    if (csrfToken) return csrfToken;
    if (!csrfPromise) {
      csrfPromise = transport.get('/api/csrf/').then(({ data }) => {
        if (!data?.csrfToken) throw new Error('CSRF initialization failed.');
        csrfToken = data.csrfToken;
        return csrfToken;
      }).finally(() => { csrfPromise = undefined; });
    }
    return csrfPromise;
  };

  const refresh = () => {
    if (!refreshPromise) {
      refreshPromise = (async () => {
        const token = await client.ensureCSRF();
        let response;
        try {
          response = await transport.post('/api/token/refresh/', {}, { headers: { 'X-CSRFToken': token } });
        } catch (error) {
          if (error.response?.data?.code !== 'csrf_failed') throw error;
          const renewedToken = await client.ensureCSRF(true);
          response = await transport.post('/api/token/refresh/', {}, { headers: { 'X-CSRFToken': renewedToken } });
        }
        csrfToken = response.data.csrfToken || csrfToken;
        generation += 1;
      })().catch((error) => {
        // Network/server failures are recoverable and must not claim logout.
        if (error.response?.status === 401) {
          sessionEnded = true;
          onSessionExpired();
        }
        throw error;
      }).finally(() => { refreshPromise = undefined; });
    }
    return refreshPromise;
  };

  client.interceptors.request.use(async (config) => {
    // Never send the masked CSRF token to an arbitrary absolute URL.
    const apiOrigin = new URL(baseURL, window.location.origin).origin;
    if (new URL(config.url, config.baseURL || baseURL).origin !== apiOrigin) {
      throw new Error('API client cannot send credentials to another origin.');
    }
    config._authGeneration = generation;
    if (unsafe(config.method)) {
      config.headers = config.headers || {};
      config.headers['X-CSRFToken'] = await client.ensureCSRF();
    }
    return config;
  });

  client.interceptors.response.use((response) => {
    if (response.data?.csrfToken) csrfToken = response.data.csrfToken;
    if (response.config.url === '/api/token/') {
      sessionEnded = false;
      generation += 1;
    }
    return response;
  }, async (error) => {
    const original = error.config;
    if (!original) throw error;
    if (error.response?.status === 403 && error.response?.data?.code === 'csrf_failed' && !original._csrfRetry) {
      original._csrfRetry = true;
      await client.ensureCSRF(true);
      return client(original);
    }
    if (error.response?.status !== 401 || original._retry || authEndpoint(original.url) || sessionEnded || loggingOut) {
      throw error;
    }
    original._retry = true; // Every waiter gets one retry, including queued requests.
    if (original._authGeneration === generation) await refresh();
    if (sessionEnded || loggingOut) throw error;
    return client(original);
  });

  client.logout = async () => {
    loggingOut = true;
    try {
      // A completed rotation must not restore cookies after logout clears them.
      if (refreshPromise) await refreshPromise.catch(() => {});
      await client.post('/api/logout/', {});
      sessionEnded = true;
      generation += 1;
    } finally {
      loggingOut = false;
    }
  };
  return client;
}

export default createBrowserClient();
