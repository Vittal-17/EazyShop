import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { BrowserRouter } from 'react-router-dom';
import Home from './Home';

const mockedUsedNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockedUsedNavigate,
}));

describe('Home Page Component', () => {
  beforeEach(() => {
    mockedUsedNavigate.mockClear();
  });

  it('renders hero title and optimized background image with high fetch priority', () => {
    render(
      <BrowserRouter>
        <Home />
      </BrowserRouter>
    );

    expect(screen.getByRole('heading', { name: /Welcome to EazyShop/i })).toBeInTheDocument();
    expect(screen.getByText(/Discover curated collections/i)).toBeInTheDocument();

    const heroImg = screen.getByAltText('EazyShop 3D eCommerce');
    expect(heroImg).toBeInTheDocument();
    expect(heroImg).toHaveAttribute('src');
    expect(heroImg).toHaveAttribute('fetchPriority', 'high');
  });

  it('navigates to /products when Start Shopping CTA is clicked', () => {
    render(
      <BrowserRouter>
        <Home />
      </BrowserRouter>
    );

    const ctaBtn = screen.getByRole('button', { name: /Start Shopping/i });
    expect(ctaBtn).toBeInTheDocument();

    fireEvent.click(ctaBtn);
    expect(mockedUsedNavigate).toHaveBeenCalledWith('/products');
  });
});
