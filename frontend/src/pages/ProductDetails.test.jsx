import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import ProductDetail from './ProductDetails';
import AuthContext from '../context/AuthContext';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

jest.mock('react-hot-toast', () => ({
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
}));

const mockAxiosInstance = {
  get: jest.fn(),
  post: jest.fn(),
};

const renderWithRouter = (ui, user = null) => {
  return render(
    <AuthContext.Provider value={{ axiosInstance: mockAxiosInstance, user }}>
      {/* MemoryRouter allows us to fake the URL parameters */}
      <MemoryRouter initialEntries={['/products/99']}>
        <Routes>
          <Route path="/products/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
};

describe('ProductDetail Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    
    mockAxiosInstance.get.mockImplementation((url) => {
      if (url === '/api/products/99/') {
        return Promise.resolve({ data: { id: 99, name: 'Mechanical Keyboard', price: '150.00', stock: 10, description: 'Clicky.' } });
      }
      if (url.includes('/api/reviews/')) {
        return Promise.resolve({ data: [{ id: 1, username: 'TestUser', rating: 5, comment: 'Great!' }] });
      }
      if (url === '/api/orders/') {
        return Promise.resolve({ data: [] }); // No purchase history
      }
      return Promise.reject(new Error('Not Found'));
    });
  });

  it('loads the product and displays reviews', async () => {
    renderWithRouter(<ProductDetail />);
    
    expect(await screen.findByText('Mechanical Keyboard')).toBeInTheDocument();
    expect(await screen.findByText('Clicky.')).toBeInTheDocument();
    
    // Verify the review loaded
    expect(await screen.findByText('"Great!"')).toBeInTheDocument();
    expect(screen.getByText('TestUser')).toBeInTheDocument();
  });
});