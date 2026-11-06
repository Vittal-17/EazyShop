import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import Products from './Products';
import AuthContext from '../context/AuthContext';
import { BrowserRouter } from 'react-router-dom';

// 1. Mock Toast to prevent DOM errors
jest.mock('react-hot-toast', () => ({
  success: jest.fn(),
  error: jest.fn(),
}));

// 2. The Bulletproof Axios Setup
const mockAxiosInstance = {
  get: jest.fn(),
  post: jest.fn(),
};

const renderWithAuth = (ui, user = null) => {
  return render(
    <AuthContext.Provider value={{ axiosInstance: mockAxiosInstance, user }}>
      <BrowserRouter>{ui}</BrowserRouter>
    </AuthContext.Provider>
  );
};

describe('Products Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    // 3. The Smart Interceptor supporting pagination query parameters
    mockAxiosInstance.get.mockImplementation((url) => {
      if (url.startsWith('/api/products/?') || url === '/api/products/') {
        return Promise.resolve({
          data: {
            count: 1,
            results: [{ id: 1, name: 'Test Laptop', price: '1000.00', stock: 5, image_url: 'fake.jpg' }]
          }
        });
      }
      if (url === '/api/categories/') {
        return Promise.resolve({ data: [{ id: 1, name: 'Electronics' }] });
      }
      return Promise.reject(new Error('Not Found'));
    });
  });

  it('renders products directly without secondary N+1 detail queries', async () => {
    renderWithAuth(<Products />);

    // Check product name and formatted price
    expect(await screen.findByText('Test Laptop')).toBeInTheDocument();
    expect(await screen.findByText('₹1,000.00')).toBeInTheDocument();

    // Verify ZERO N+1 secondary requests were made
    const calls = mockAxiosInstance.get.mock.calls.map(c => c[0]);
    expect(calls.some(url => url === '/api/products/1/')).toBe(false);
  });

  it('filters out products when out of stock toggle is clicked', async () => {
    // Return an out-of-stock item directly in the catalog payload
    mockAxiosInstance.get.mockImplementation((url) => {
      if (url.includes('in_stock=true')) {
        return Promise.resolve({ data: { count: 0, results: [] } });
      }
      if (url.startsWith('/api/products/?') || url === '/api/products/') {
        return Promise.resolve({
          data: {
            count: 1,
            results: [{ id: 2, name: 'Dead Item', price: '10.00', stock: 0 }]
          }
        });
      }
      if (url === '/api/categories/') {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve({ data: [] });
    });

    renderWithAuth(<Products />);
    expect(await screen.findByText('Dead Item')).toBeInTheDocument();

    // Open filters and click "In Stock Only"
    fireEvent.click(screen.getByText(/Filters/i));
    const stockToggle = await screen.findByLabelText(/In Stock Only/i);
    fireEvent.click(stockToggle);

    // The item should disappear
    await waitFor(() => {
      expect(screen.queryByText('Dead Item')).not.toBeInTheDocument();
    });
  });
});
