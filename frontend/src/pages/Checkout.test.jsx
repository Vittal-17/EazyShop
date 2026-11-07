import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import Checkout from './Checkout';
import AuthContext from '../context/AuthContext';
import { toast } from 'react-hot-toast';

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
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Checkout />
      </MemoryRouter>
    </AuthContext.Provider>
  );
};

describe('Checkout Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
    window.Razorpay = jest.fn().mockImplementation(() => ({
      open: jest.fn(),
      on: jest.fn(),
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
  it('failed attempt can retry the same key and provider order without cancellation', async () => {
    const handlers = {};
    window.Razorpay.mockImplementation(() => ({ open: jest.fn(), on: (event, fn) => { handlers[event] = fn; } }));
    mockAxiosInstance.post.mockResolvedValue({ data: {
      order_id: 999, razorpay_order_id: 'order_retry', amount: 10000, currency: 'INR', key_id: 'fixture'
    } });
    renderCheckout();
    await screen.findByText('Mouse');
    fireEvent.click(screen.getByRole('button', { name: /Place Secure Order/i }));
    await waitFor(() => expect(window.Razorpay).toHaveBeenCalledTimes(1));
    const key = mockAxiosInstance.post.mock.calls[0][1].idempotency_key;
    await act(async () => {
      handlers['payment.failed']();
      await window.Razorpay.mock.calls[0][0].modal.ondismiss();
    });
    expect(mockAxiosInstance.post.mock.calls.some(([url]) => url.endsWith('/cancel/'))).toBe(false);
    expect(sessionStorage.getItem('eazyshop:purchase:merchandise:1')).toBe(key);
    fireEvent.click(screen.getByRole('button', { name: /Place Secure Order/i }));
    await waitFor(() => expect(window.Razorpay).toHaveBeenCalledTimes(2));
    expect(mockAxiosInstance.post.mock.calls[1][1].idempotency_key).toBe(key);
    expect(window.Razorpay.mock.calls[1][0].order_id).toBe('order_retry');
  });

  it('unresolved capture followed by failure/dismissal never cancels or discards the key', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const handlers = {};
      window.Razorpay.mockImplementation(() => ({ open: jest.fn(), on: (event, fn) => { handlers[event] = fn; } }));
      mockAxiosInstance.post.mockImplementation(url => url.endsWith('create-razorpay-order/')
        ? Promise.resolve({ data: { order_id: 999, razorpay_order_id: 'order_unknown', amount: 10000, currency: 'INR', key_id: 'fixture' } })
        : Promise.reject(new Error('Unknown captured outcome')));
      renderCheckout();
      await screen.findByText('Mouse');
      fireEvent.click(screen.getByRole('button', { name: /Place Secure Order/i }));
      await waitFor(() => expect(window.Razorpay).toHaveBeenCalledTimes(1));
      const key = mockAxiosInstance.post.mock.calls[0][1].idempotency_key;
      const options = window.Razorpay.mock.calls[0][0];
      await act(async () => {
        await options.handler({ razorpay_payment_id: 'pay_unknown', razorpay_order_id: 'order_unknown', razorpay_signature: 'fixture' });
        handlers['payment.failed']();
        await options.modal.ondismiss();
      });
      expect(sessionStorage.getItem('eazyshop:purchase:merchandise:1')).toBe(key);
      expect(mockAxiosInstance.post.mock.calls.some(([url]) => url.endsWith('/cancel/'))).toBe(false);
      expect(consoleErrorSpy).toHaveBeenCalledWith('Verification error:', expect.any(Error));
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  it('shows a request conflict and preserves the unresolved key without opening checkout', async () => {
    const message = 'This purchase key belongs to different items. Restore the original request; do not replace this key.';
    sessionStorage.setItem('eazyshop:purchase:merchandise:1', 'unresolved-order');
    mockAxiosInstance.post.mockRejectedValue({ response: { status: 409, data: {
      code: 'purchase_request_conflict', error: message
    } } });
    renderCheckout();
    await screen.findByText('Mouse');
    for (let attempt = 1; attempt <= 2; attempt += 1) {
      fireEvent.click(screen.getByRole('button', { name: /Place Secure Order/i }));
      await waitFor(() => expect(mockAxiosInstance.post).toHaveBeenCalledTimes(attempt));
      await waitFor(() => expect(screen.getByRole('button', { name: /Place Secure Order/i })).not.toBeDisabled());
    }
    expect(toast.error).toHaveBeenCalledWith(`❌ ${message}`);
    expect(sessionStorage.getItem('eazyshop:purchase:merchandise:1')).toBe('unresolved-order');
    expect(mockAxiosInstance.post.mock.calls.every(([, data]) => data.idempotency_key === 'unresolved-order')).toBe(true);
    expect(window.Razorpay).not.toHaveBeenCalled();
  });

});
