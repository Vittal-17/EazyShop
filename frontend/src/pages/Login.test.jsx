import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import Login from './Login';
import AuthContext from '../context/AuthContext';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { toast } from 'react-hot-toast'; // Import real toast to assert on

// 🚨 THE FIX: Mocking toast cleanly without hitting the Temporal Dead Zone
jest.mock('react-hot-toast', () => {
  const t = jest.fn();
  t.success = jest.fn();
  t.error = jest.fn();
  return { toast: t, Toaster: () => null };
});

const mockLoginUser = jest.fn();

const renderLogin = () => {
  return render(
    <AuthContext.Provider value={{ loginUser: mockLoginUser }}>
      <MemoryRouter initialEntries={[{ pathname: '/login', state: { from: '/checkout' } }]}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/checkout" element={<div>Fake Checkout Page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
};

describe('Login Component', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  it('prevents submission if fields are empty', async () => {
    renderLogin();
    fireEvent.click(screen.getByRole('button', { name: /Login/i }));
    
    expect(toast.error).toHaveBeenCalledWith(
      expect.stringContaining('Please fill in all fields'),
      expect.any(Object)
    );
    expect(mockLoginUser).not.toHaveBeenCalled();
  });

  it('calls loginUser and processes success', async () => {
    mockLoginUser.mockResolvedValueOnce(true);
    renderLogin();
    
    fireEvent.change(screen.getByPlaceholderText('Email'), { target: { value: 'test@test.com' } });
    fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'password123' } });
    fireEvent.click(screen.getByRole('button', { name: /Login/i }));
    
    await waitFor(() => {
      expect(mockLoginUser).toHaveBeenCalledWith('test@test.com', 'password123');
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('Login successful'), expect.any(Object));
    });
  });
});