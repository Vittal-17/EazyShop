import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import Dashboard from './Dashboard';
import AuthContext from '../context/AuthContext';
import { BrowserRouter } from 'react-router-dom';
import { toast } from 'react-hot-toast';

jest.mock('react-hot-toast', () => {
  const t = jest.fn();
  t.success = jest.fn();
  t.error = jest.fn();
  return { toast: t };
});

const mockAxiosInstance = { get: jest.fn(), post: jest.fn(), patch: jest.fn() };
const mockUser = { id: 1, username: 'testuser', email: 'test@test.com' };

const renderDashboard = () => render(
  <AuthContext.Provider value={{ axiosInstance: mockAxiosInstance, user: mockUser }}>
    <BrowserRouter><Dashboard /></BrowserRouter>
  </AuthContext.Provider>
);

describe('Dashboard Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAxiosInstance.get.mockImplementation((url) => {
      if (url === '/api/orders/') return Promise.resolve({ data: [{ id: 501, status: 'pending', total_price: '120.00', user: 1 }] });
      if (url === '/api/reviews/') return Promise.resolve({ data: [] });
      if (url === `/api/users/1/`) return Promise.resolve({ data: { phone: '5551234567' } });
      if (url === '/api/addresses/') return Promise.resolve({ data: [{ id: 1, label: 'Home', full_address: '123 Main St', is_default: true }] });
      return Promise.resolve({ data: [] }); 
    });
  });

  it('renders all concurrent data across tabs', async () => {
    renderDashboard();
    await waitFor(() => expect(screen.queryByText('Loading...')).not.toBeInTheDocument());
    expect(screen.getByText('Order #501')).toBeInTheDocument();
    
    fireEvent.click(screen.getByText(/Profile Settings/i));
    expect(await screen.findByText('123 Main St')).toBeInTheDocument();
  });

  it('handles the order cancellation flow', async () => {
    mockAxiosInstance.post.mockResolvedValueOnce({});
    renderDashboard();
    
    await screen.findByText('Order #501');
    fireEvent.click(screen.getByText('Cancel Order'));
    
    expect(await screen.findByText(/Are you sure you want to cancel this order/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText('Yes, Cancel'));
    
    await waitFor(() => {
      expect(mockAxiosInstance.post).toHaveBeenCalledWith('/api/orders/501/cancel/');
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('cancelled successfully'));
    });
  });
});