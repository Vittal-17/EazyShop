import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import OrderSuccess from './OrderSuccess';
import AuthContext from '../context/AuthContext';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

const mockAxiosInstance = {
  get: jest.fn(),
};

const renderWithRouter = (initialEntries) => {
  return render(
    <AuthContext.Provider value={{ axiosInstance: mockAxiosInstance }}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/order-success/:orderId" element={<OrderSuccess />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
};

describe('OrderSuccess Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders order details correctly from router location.state', () => {
    const mockState = {
      order: { total_price: '500.00' },
      payment: { payment_method: 'credit_card', transaction_id: 'txn_12345' },
      userAddress: '123 Testing Lane',
      userPhone: '(555) 123-4567'
    };

    renderWithRouter([{ pathname: '/order-success/999', state: mockState }]);

    expect(screen.getByText('Payment Successful!')).toBeInTheDocument();
    expect(screen.getByText('#999')).toBeInTheDocument();
    expect(screen.getByText('txn_12345')).toBeInTheDocument();
    expect(screen.getByText('123 Testing Lane')).toBeInTheDocument();
    expect(screen.getByText('₹500.00')).toBeInTheDocument();
    expect(mockAxiosInstance.get).not.toHaveBeenCalled();
  });

  it('hydrates order details via API fallback on browser refresh when location.state is missing', async () => {
    mockAxiosInstance.get.mockResolvedValueOnce({
      data: {
        id: 888,
        total_price: '750.00',
        shipping_address: '456 Refreshed Blvd',
        contact_phone: '9876543210',
        payment: [{ payment_method: 'razorpay', transaction_id: 'pay_refreshed_888' }]
      }
    });

    // Render WITHOUT router state (simulating refresh or direct link)
    renderWithRouter(['/order-success/888']);

    expect(screen.getByText('Payment Successful!')).toBeInTheDocument();
    expect(screen.getByText('#888')).toBeInTheDocument();

    // Verify fallback API call was made
    await waitFor(() => {
      expect(mockAxiosInstance.get).toHaveBeenCalledWith('/api/orders/888/');
    });

    // Verify hydrated receipt details
    expect(await screen.findByText('pay_refreshed_888')).toBeInTheDocument();
    expect(await screen.findByText('456 Refreshed Blvd')).toBeInTheDocument();
    expect(await screen.findByText('9876543210')).toBeInTheDocument();
    expect(await screen.findByText('₹750.00')).toBeInTheDocument();
  });
});
