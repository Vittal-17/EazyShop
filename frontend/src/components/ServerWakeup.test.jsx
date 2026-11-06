import { render, screen, act, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import ServerWakeup from './ServerWakeup';
import AuthContext from '../context/AuthContext';

jest.mock('framer-motion', () => {
  const actual = jest.requireActual('framer-motion');
  return {
    ...actual,
    AnimatePresence: ({ children }) => <>{children}</>,
  };
});

describe('ServerWakeup Component', () => {
  let mockAxiosInstance;

  beforeEach(() => {
    jest.useFakeTimers();
    mockAxiosInstance = {
      get: jest.fn().mockImplementation(() => new Promise(() => {})), // never resolves initially
    };
  });

  afterEach(() => {
    act(() => {
      jest.runOnlyPendingTimers();
    });
    jest.useRealTimers();
  });

  it('does not display wakeup modal during fast connection under 3500ms', () => {
    render(
      <AuthContext.Provider value={{ axiosInstance: mockAxiosInstance }}>
        <ServerWakeup />
      </AuthContext.Provider>
    );

    // Advance 3000ms (still within threshold)
    act(() => {
      jest.advanceTimersByTime(3000);
    });

    expect(screen.queryByText(/Waking EazyShop Server/i)).not.toBeInTheDocument();
  });

  it('displays wakeup modal after 3500ms delay and allows manual dismissal', () => {
    render(
      <AuthContext.Provider value={{ axiosInstance: mockAxiosInstance }}>
        <ServerWakeup />
      </AuthContext.Provider>
    );

    // Advance past 3500ms
    act(() => {
      jest.advanceTimersByTime(3600);
    });

    expect(screen.getByText(/Waking EazyShop Server/i)).toBeInTheDocument();
    expect(screen.getByText(/Continue Browsing/i)).toBeInTheDocument();

    // Click "Continue Browsing"
    fireEvent.click(screen.getByText(/Continue Browsing/i));
    act(() => { jest.advanceTimersByTime(1000); });

    expect(screen.queryByText(/Waking EazyShop Server/i)).not.toBeInTheDocument();
  });

  it('automatically hides modal when server responds with 200 OK', async () => {
    let resolveServerPing;
    mockAxiosInstance.get = jest.fn().mockImplementation(() => new Promise((res) => {
      resolveServerPing = res;
    }));

    render(
      <AuthContext.Provider value={{ axiosInstance: mockAxiosInstance }}>
        <ServerWakeup />
      </AuthContext.Provider>
    );

    // Trigger modal
    act(() => {
      jest.advanceTimersByTime(3600);
    });
    expect(screen.getByText(/Waking EazyShop Server/i)).toBeInTheDocument();

    // Resolve server response
    await act(async () => {
      resolveServerPing({ data: [] });
    });

    expect(screen.queryByText(/Waking EazyShop Server/i)).not.toBeInTheDocument();
  });
});
