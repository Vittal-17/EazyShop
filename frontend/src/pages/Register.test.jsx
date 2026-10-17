import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import Register from './Register';
import AuthContext from '../context/AuthContext';
import { BrowserRouter } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'react-hot-toast';

jest.mock('react-hot-toast', () => {
  const t = jest.fn();
  t.success = jest.fn();
  t.error = jest.fn();
  return { toast: t, Toaster: () => null };
});

const mockLoginUser = jest.fn();

const renderRegister = () => render(
  <AuthContext.Provider value={{ loginUser: mockLoginUser }}>
    <BrowserRouter><Register /></BrowserRouter>
  </AuthContext.Provider>
);

describe('Register Component', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  it('shows password rules when focused and validates correctly', async () => {
    renderRegister();
    
    const passwordInput = screen.getByPlaceholderText('Password');
    
    // 1. Focus the input to reveal the rules
    fireEvent.focus(passwordInput);
    expect(screen.getByText(/At least 8 characters/i)).toBeInTheDocument();
    
    // 2. Type an invalid password (too short, all numbers)
    fireEvent.change(passwordInput, { target: { value: '123' } });
    
    // 3. Try to submit
    fireEvent.click(screen.getByRole('button', { name: /Register/i }));
    
    // It should trigger a toast error instead of hitting the API
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Your password must contain at least 8 characters.'),
        expect.any(Object)
      );
      expect(axios.post).not.toHaveBeenCalled();
    });
  });

  it('registers successfully and logs the user in', async () => {
    // Mock the backend responding with 201 Created
    axios.post.mockResolvedValueOnce({ status: 201 });
    mockLoginUser.mockResolvedValueOnce(true);
    
    renderRegister();
    
    fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'testuser' } });
    fireEvent.change(screen.getByPlaceholderText('Email'), { target: { value: 'test@test.com' } });
    fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'StrongPass123!' } });
    fireEvent.change(screen.getByPlaceholderText('Confirm Password'), { target: { value: 'StrongPass123!' } });
    
    fireEvent.click(screen.getByRole('button', { name: /Register/i }));
    
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalled();
      expect(mockLoginUser).toHaveBeenCalledWith('test@test.com', 'StrongPass123!');
      expect(toast.success).toHaveBeenCalled();
    });
  });
});