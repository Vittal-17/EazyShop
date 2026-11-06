import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import Checkout from './Checkout';
import AuthContext from '../context/AuthContext';

jest.mock('react-hot-toast', () => {
  const t = {
    success: jest.fn(),
    error: jest.fn(),
    loading: jest.fn(),
    dismiss: jest.fn(),
  };
  return {
    __esModule: true,
    default: t,
    toast: t,
  };
});

const mockAxiosInstance = {
  get: jest.fn(),
  post: jest.fn(),
};

const mockUser = { id: 1, username: 'buyer', email: 'buyer@test.com' };

const renderCheckout = () => {
  return render(
    <AuthContext.Provider value={{ axiosInstance: mockAxiosInstance, user: mockUser }}>
      <MemoryRouter>
        <Checkout />
      </MemoryRouter>
    </AuthContext.Provider>
  );
};

describe('Checkout Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.Razorpay = jest.fn().mockImplementation(() => ({
      open: jest.fn(),
    }));

    mockAxiosInstance.get.mockImplementation((url) => {
      if (url === '/api/cart-items/') {
        return Promise.resolve({
          data: [
            { id: 1, product: { id: 1 }, product_name: 'Mouse', quantity: 2, price: '50.00' }
          ]
        });
      }
      if (url === '/api/users/1/') {
        return Promise.resolve({ data: { phone: '1234567890', wallet_balance: '0.00' } });
      }
      if (url === '/api/addresses/') {
        return Promise.resolve({
          data: [
            { id: 1, label: 'Home', full_address: '123 Test St', is_default: true }
          ]
        });
      }
      return Promise.reject(new Error('Not Found'));
    });
  });

  it('loads cart, address, verified phone and sends sanitized payload on order placement', async () => {
    mockAxiosInstance.post.mockResolvedValueOnce({
      data: {
        order_id: 999,
        razorpay_order_id: 'order_test_999',
        amount: 10000,
        currency: 'INR',
        key: 'rzp_test',
        payment: { id: 1 }
      }
    });

    renderCheckout();

    // 1. Verify Cart item loaded
    expect(await screen.findByText('Mouse')).toBeInTheDocument();

    // 2. Verify Address Loaded
    expect(await screen.findByText('123 Test St')).toBeInTheDocument();

    // 3. Verify verified phone number is displayed
    expect(await screen.findByText('1234567890')).toBeInTheDocument();

    // 4. Verify Total Price calculation (₹50 * 2 = ₹100)
    expect(screen.getAllByText('₹100.00').length).toBeGreaterThanOrEqual(1);

    // 5. Click "Place Secure Order"
    const placeOrderBtn = screen.getByRole('button', { name: /Place Secure Order/i });
    fireEvent.click(placeOrderBtn);

    // 6. Assert create-razorpay-order received sanitized payload without client-side price
    await waitFor(() => {
      expect(mockAxiosInstance.post).toHaveBeenCalledWith(
        '/api/orders/create-razorpay-order/',
        expect.objectContaining({
          shipping_address: expect.stringContaining('123 Test St'),
          contact_phone: '1234567890',
          order_items: [{ product: 1, quantity: 2 }],
        })
      );
    });

    // Ensure price is NOT in order_items payload
    const callPayload = mockAxiosInstance.post.mock.calls[0][1];
    expect(callPayload.order_items[0]).not.toHaveProperty('price');
  });
});
