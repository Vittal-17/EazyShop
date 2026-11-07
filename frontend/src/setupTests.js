// src/setupTests.js
import '@testing-library/jest-dom';

// Intercept all Axios imports globally and avoid the TDZ bug
jest.mock('axios', () => {
  // 1. Define it INSIDE the mock block so it gets hoisted together
  const mockAxiosInstance = {
    get: jest.fn(() => Promise.resolve({ data: [] })),
    post: jest.fn(() => Promise.resolve({ data: {} })),
    put: jest.fn(() => Promise.resolve({ data: {} })),
    delete: jest.fn(() => Promise.resolve({ data: {} })),
    patch: jest.fn(() => Promise.resolve({ data: {} })),
    interceptors: {
      request: { use: jest.fn(), eject: jest.fn() },
      response: { use: jest.fn(), eject: jest.fn() }
    }
  };

  return {
    __esModule: true,
    default: {
      create: jest.fn(() => mockAxiosInstance),
      ...mockAxiosInstance
    },
    create: jest.fn(() => mockAxiosInstance),
    ...mockAxiosInstance
  };
});
// jsdom in react-scripts lacks Web Crypto; use Node's implementation in tests.
Object.defineProperty(global, 'crypto', { value: require('crypto').webcrypto, configurable: true });

// Mock missing browser APIs in Jest/jsdom environment; retain real browser behavior in production.
if (typeof window !== 'undefined') {
  window.scrollTo = jest.fn();
}
