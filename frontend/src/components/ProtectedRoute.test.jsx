import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import ProtectedRoute from './ProtectedRoute';
import AuthContext from '../context/AuthContext';

const renderWithContext = (ui, { user = null, loading = false } = {}, initialEntry = '/protected') => {
  return render(
    <AuthContext.Provider value={{ user, loading }}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/login" element={<div>Login Page</div>} />
          <Route path="/" element={<div>Home Page</div>} />
          <Route path="/protected" element={ui} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
};

describe('ProtectedRoute Component', () => {
  it('renders loading spinner and text while auth is resolving', () => {
    renderWithContext(
      <ProtectedRoute>
        <div>Secret Content</div>
      </ProtectedRoute>,
      { user: null, loading: true }
    );

    expect(screen.getByText('Checking access...')).toBeInTheDocument();
    expect(screen.queryByText('Secret Content')).not.toBeInTheDocument();
  });

  it('redirects unauthenticated user to /login when loading finishes', () => {
    renderWithContext(
      <ProtectedRoute>
        <div>Secret Content</div>
      </ProtectedRoute>,
      { user: null, loading: false }
    );

    expect(screen.getByText('Login Page')).toBeInTheDocument();
    expect(screen.queryByText('Secret Content')).not.toBeInTheDocument();
  });

  it('renders protected child content for authenticated regular user', () => {
    renderWithContext(
      <ProtectedRoute>
        <div>Secret Content</div>
      </ProtectedRoute>,
      { user: { id: 1, username: 'testuser', role: 'customer' }, loading: false }
    );

    expect(screen.getByText('Secret Content')).toBeInTheDocument();
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument();
  });

  it('redirects non-admin user to home / when route is adminOnly', () => {
    renderWithContext(
      <ProtectedRoute adminOnly>
        <div>Admin Dashboard</div>
      </ProtectedRoute>,
      { user: { id: 2, username: 'shopper', role: 'customer' }, loading: false }
    );

    expect(screen.getByText('Home Page')).toBeInTheDocument();
    expect(screen.queryByText('Admin Dashboard')).not.toBeInTheDocument();
  });

  it('renders admin content for user with admin role', () => {
    renderWithContext(
      <ProtectedRoute adminOnly>
        <div>Admin Dashboard</div>
      </ProtectedRoute>,
      { user: { id: 3, username: 'superadmin', role: 'admin' }, loading: false }
    );

    expect(screen.getByText('Admin Dashboard')).toBeInTheDocument();
  });
});
