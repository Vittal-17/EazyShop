import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import Checkout from './Checkout';
import AuthContext from '../context/AuthContext';
import { BrowserRouter } from 'react-router-dom';

jest.mock('react-hot-toast', () => ({
  success: jest.fn(),
  error: jest.fn(),
}));

const mockAxiosInstance = {
  get: jest.fn(),
  post: jest.fn(),
};

const mockUser = { id: 1, username: 'buyer', email: 'buyer@test.com' };

const renderCheckout = () => {
  return render(
    <AuthContext.Provider value={{ axiosInstance: mockAxiosInstance, user: mockUser }}>
      <BrowserRouter><Checkout /></BrowserRouter>
    </AuthContext.Provider>
  );
};

describe('Checkout Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    
    mockAxiosInstance.get.mockImplementation((url) => {
      if (url === '/api/cart-items/') {
        return Promise.resolve({ data: [
          { id: 1, product: 1, product_name: 'Mouse', quantity: 2, price: '50.00' }
        ]});
      }
      if (url === '/api/users/1/') {
        return Promise.resolve({ data: { phone: '1234567890' } });
      }
      if (url === '/api/addresses/') {
        return Promise.resolve({ data: [
          { id: 1, label: 'Home', full_address: '123 Test St', is_default: true }
        ]});
      }
      return Promise.reject(new Error('Not Found'));
    });
  });

  it('loads cart, address, and allows order placement', async () => {
    renderCheckout();
    
    // 1. Verify Cart Loaded
    expect(await screen.findByText('Mouse')).toBeInTheDocument();
    
    // 2. Verify Address Loaded
    expect(await screen.findByText('123 Test St')).toBeInTheDocument();
    
    // 3. Verify phone number was auto-formatted and populated
    const phoneInput = screen.getByPlaceholderText('(XXX) XXX-XXXX');
    expect(phoneInput.value).toBe('(123) 456-7890');

    // 4. Verify Total Price calculation (₹50 * 2 = ₹100)
    expect(screen.getByText('₹100.00')).toBeInTheDocument();
    
    // 5. Test clicking "Place Order" (Requires mocking the post requests)
    mockAxiosInstance.post.mockResolvedValueOnce({ data: { id: 999, total_price: '100.00' } }); // Mock Order Creation
    
    const placeOrderBtn = screen.getByRole('button', { name: /Place Order Now/i });
    fireEvent.click(placeOrderBtn);
    
    // It should go into "Processing" state
    expect(await screen.findByText('Processing Payment')).toBeInTheDocument();
  });
});