import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import Cart from './Cart';
import AuthContext from '../context/AuthContext';
import { BrowserRouter } from 'react-router-dom';
import { toast } from 'react-hot-toast';

jest.mock('react-hot-toast', () => {
  const t = jest.fn();
  t.success = jest.fn();
  t.error = jest.fn();
  return { toast: t };
});

const mockAxiosInstance = { get: jest.fn(), patch: jest.fn(), delete: jest.fn() };
const mockUser = { id: 1, username: 'buyer' };

const renderCart = () => render(
  <AuthContext.Provider value={{ axiosInstance: mockAxiosInstance, user: mockUser }}>
    <BrowserRouter><Cart /></BrowserRouter>
  </AuthContext.Provider>
);

describe('Cart Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers(); 
    mockAxiosInstance.get.mockImplementation((url) => {
      if (url === '/api/cart-items/') return Promise.resolve({ data: [{ id: 10, product: 1, product_name: 'Gaming Mouse', quantity: 1, price: '50.00', product_stock: 5 }] });
      if (url === '/api/wishlist/') return Promise.resolve({ data: [] });
      return Promise.reject(new Error('Not Found'));
    });
  });

  afterEach(() => {
    act(() => { jest.runOnlyPendingTimers(); });
    jest.useRealTimers(); 
  });

  it('debounces the quantity update API call', async () => {
    mockAxiosInstance.patch.mockResolvedValueOnce({});
    renderCart();
    
    await screen.findByText('Gaming Mouse');
    const incrementBtn = screen.getByText('➕');
    fireEvent.click(incrementBtn);
    fireEvent.click(incrementBtn);

    act(() => { jest.advanceTimersByTime(500); });

    await waitFor(() => {
      expect(mockAxiosInstance.patch).toHaveBeenCalledTimes(1);
      expect(mockAxiosInstance.patch).toHaveBeenCalledWith('/api/cart-items/10/', { quantity: 3 });
    });
  });
});