import { render, screen, act, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { BrowserRouter } from 'react-router-dom';
import Navbar from './Navbar';
import AuthContext from '../context/AuthContext';

describe('Navbar Component with Real-Time Cart Badge', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  it('renders navigation links and no badge when cart is empty', async () => {
    render(
      <AuthContext.Provider value={{ user: null, logoutUser: jest.fn() }}>
        <BrowserRouter>
          <Navbar />
        </BrowserRouter>
      </AuthContext.Provider>
    );

    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.getByText('Store')).toBeInTheDocument();
    expect(screen.getByText('Cart')).toBeInTheDocument();
    expect(screen.queryByTestId('cart-badge')).not.toBeInTheDocument();
  });

  it('displays guest cart item count from localStorage', async () => {
    localStorage.setItem(
      'tempCart',
      JSON.stringify([
        { id: '1', quantity: 2 },
        { id: '2', quantity: 3 },
      ])
    );

    render(
      <AuthContext.Provider value={{ user: null, logoutUser: jest.fn() }}>
        <BrowserRouter>
          <Navbar />
        </BrowserRouter>
      </AuthContext.Provider>
    );

    const badge = await screen.findByTestId('cart-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('5');
  });

  it('fetches authenticated user cart count from api/cart-items/', async () => {
    const mockAxios = {
      get: jest.fn().mockResolvedValue({
        data: [
          { id: 101, quantity: 4 },
          { id: 102, quantity: 1 },
        ],
      }),
    };

    render(
      <AuthContext.Provider
        value={{
          user: { id: 1, username: 'testuser', role: 'customer' },
          logoutUser: jest.fn(),
          axiosInstance: mockAxios,
        }}
      >
        <BrowserRouter>
          <Navbar />
        </BrowserRouter>
      </AuthContext.Provider>
    );

    const badge = await screen.findByTestId('cart-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('5');
    expect(mockAxios.get).toHaveBeenCalledWith('/api/cart-items/');
  });

  it('updates dynamically in real-time when cart-updated event is dispatched', async () => {
    render(
      <AuthContext.Provider value={{ user: null, logoutUser: jest.fn() }}>
        <BrowserRouter>
          <Navbar />
        </BrowserRouter>
      </AuthContext.Provider>
    );

    expect(screen.queryByTestId('cart-badge')).not.toBeInTheDocument();

    // Now user adds items to cart
    localStorage.setItem(
      'tempCart',
      JSON.stringify([{ id: '3', quantity: 8 }])
    );

    // Dispatch the custom event
    await act(async () => {
      window.dispatchEvent(new Event('cart-updated'));
    });

    const badge = await screen.findByTestId('cart-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('8');
  });

  it('displays 99+ when total items exceed 99', async () => {
    localStorage.setItem(
      'tempCart',
      JSON.stringify([{ id: '1', quantity: 150 }])
    );

    render(
      <AuthContext.Provider value={{ user: null, logoutUser: jest.fn() }}>
        <BrowserRouter>
          <Navbar />
        </BrowserRouter>
      </AuthContext.Provider>
    );

    const badge = await screen.findByTestId('cart-badge');
    expect(badge).toHaveTextContent('99+');
  });
});
