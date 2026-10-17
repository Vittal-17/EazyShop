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
    
    // 3. The Smart Interceptor
    mockAxiosInstance.get.mockImplementation((url) => {
      if (url === '/api/products/') {
        return Promise.resolve({ data: [{ id: 1, name: 'Test Laptop', price: '1000.00' }] });
      }
      if (url === '/api/products/1/') {
        return Promise.resolve({ data: { id: 1, image_url: 'fake.jpg', stock: 5 } });
      }
      if (url === '/api/categories/') {
        return Promise.resolve({ data: [{ id: 1, name: 'Electronics' }] });
      }
      return Promise.reject(new Error('Not Found'));
    });
  });

  it('renders products and categories successfully', async () => {
    renderWithAuth(<Products />);
    
    // Use findByText to wait for the Promise.all to resolve
    expect(await screen.findByText('Test Laptop')).toBeInTheDocument();
    expect(await screen.findByText('₹1000.00')).toBeInTheDocument();
  });

  it('filters out products when out of stock toggle is clicked', async () => {
    // Override the mock to return an out-of-stock item for this specific test
    mockAxiosInstance.get.mockImplementation((url) => {
      if (url === '/api/products/') return Promise.resolve({ data: [{ id: 2, name: 'Dead Item', price: '10' }] });
      if (url === '/api/products/2/') return Promise.resolve({ data: { id: 2, stock: 0 } });
      if (url === '/api/categories/') return Promise.resolve({ data: [] });
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