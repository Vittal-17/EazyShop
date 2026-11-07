import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import NotFound from './NotFound';

const mockedUsedNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockedUsedNavigate,
}));

describe('NotFound Page Component', () => {
  beforeEach(() => {
    mockedUsedNavigate.mockClear();
  });

  it('renders 404 badge, heading, and description cleanly', () => {
    render(
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <NotFound />
      </BrowserRouter>
    );

    expect(screen.getByText(/404 Error/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Page Not Found/i })).toBeInTheDocument();
    expect(screen.getByText(/doesn't exist, has been removed/i)).toBeInTheDocument();
  });

  it('navigates to / when Return to Home button is clicked', () => {
    render(
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <NotFound />
      </BrowserRouter>
    );

    const homeBtn = screen.getByRole('button', { name: /Return to Home/i });
    expect(homeBtn).toBeInTheDocument();

    fireEvent.click(homeBtn);
    expect(mockedUsedNavigate).toHaveBeenCalledWith('/');
  });

  it('navigates to /products when Browse Products button is clicked', () => {
    render(
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <NotFound />
      </BrowserRouter>
    );

    const browseBtn = screen.getByRole('button', { name: /Browse Products/i });
    expect(browseBtn).toBeInTheDocument();

    fireEvent.click(browseBtn);
    expect(mockedUsedNavigate).toHaveBeenCalledWith('/products');
  });
});
