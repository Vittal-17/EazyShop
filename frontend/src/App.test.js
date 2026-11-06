// src/App.test.js
import { render, screen } from '@testing-library/react';
import App from './App';

// 1. The Nuclear Override: Mock Axios
jest.mock('axios', () => {
  const mockInstance = {
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
      create: () => mockInstance,
      ...mockInstance
    },
    create: () => mockInstance,
    ...mockInstance
  };
});

// 2. THE FIX: Mock Toast AND the useToasterStore hook
jest.mock('react-hot-toast', () => ({
  Toaster: () => null,
  toast: { success: jest.fn(), error: jest.fn(), dismiss: jest.fn() },
  useToasterStore: () => ({ toasts: [] }) // <-- Prevents the AppToaster crash
}));

describe('Main App Component', () => {
  it('renders the application without crashing', async () => {
    render(<App />);

    // Look for the brand heading to ensure the home page loaded
    const brandHeading = await screen.findByRole('heading', { name: /Welcome to EazyShop/i });
    expect(brandHeading).toBeInTheDocument();
  });
});
