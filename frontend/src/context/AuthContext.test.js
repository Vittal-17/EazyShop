import { useContext } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext, AuthProvider } from './AuthContext';
import api from '../utils/axios';
import toast from 'react-hot-toast';

jest.mock('../utils/axios', () => ({
  setSessionExpiredHandler: jest.fn(() => () => {}), get: jest.fn(), post: jest.fn(), logout: jest.fn(),
}));
jest.mock('react-hot-toast', () => ({ __esModule: true, default: Object.assign(jest.fn(), { error: jest.fn(), success: jest.fn() }) }));
function Probe() {
  const { user, loading, loginUser, logoutUser } = useContext(AuthContext);
  return <><span>{loading ? 'loading' : user?.username || 'anonymous'}</span>
    <button onClick={() => loginUser('fixture@example.invalid', 'fixture')}>login</button>
    <button onClick={logoutUser}>logout</button></>;
}
const fixture = { id: 1, username: 'fixture' };
beforeEach(() => {
  localStorage.clear(); jest.clearAllMocks();
  api.get.mockResolvedValue({ data: fixture });
});
function mount() { render(<MemoryRouter><AuthProvider><Probe /></AuthProvider></MemoryRouter>); }

it('removes legacy JWT storage and confirms cookies before declaring login success', async () => {
  localStorage.setItem('access_token', 'obsolete'); localStorage.setItem('refresh_token', 'obsolete');
  api.post.mockResolvedValue({ status: 200, data: { user: fixture } });
  mount(); fireEvent.click(screen.getByText('login'));
  await screen.findByText('fixture');
  expect(api.get).toHaveBeenCalledWith('/api/users/1/');
  expect(localStorage.getItem('access_token')).toBeNull();
  expect(localStorage.getItem('refresh_token')).toBeNull();
});

it('does not claim login success if the browser rejects its session cookies', async () => {
  api.post.mockResolvedValue({ status: 200, data: { user: fixture } });
  api.get.mockRejectedValue({ response: { status: 401 } });
  mount(); fireEvent.click(screen.getByText('login'));
  await waitFor(() => expect(api.get).toHaveBeenCalled());
  expect(screen.getByText('anonymous')).toBeInTheDocument();
  expect(localStorage.getItem('user')).toBeNull();
});

it('retains user state and reports failure when server logout fails', async () => {
  localStorage.setItem('user', JSON.stringify(fixture));
  api.logout.mockRejectedValue(new Error('offline'));
  mount(); await screen.findByText('fixture'); fireEvent.click(screen.getByText('logout'));
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Logout failed. Please retry.'));
  expect(screen.getByText('fixture')).toBeInTheDocument();
  expect(localStorage.getItem('user')).not.toBeNull();
});

it('clears user state only after confirmed logout', async () => {
  localStorage.setItem('user', JSON.stringify(fixture));
  api.logout.mockResolvedValue();
  mount(); await screen.findByText('fixture'); fireEvent.click(screen.getByText('logout'));
  await screen.findByText('anonymous');
  expect(localStorage.getItem('user')).toBeNull();
});

it('does not restore a stale profile after confirmed logout', async () => {
  localStorage.setItem('user', JSON.stringify(fixture));
  let completeProfile;
  api.get.mockImplementation(() => new Promise(resolve => { completeProfile = resolve; }));
  api.logout.mockResolvedValue();
  mount();
  fireEvent.click(screen.getByText('logout'));
  await screen.findByText('anonymous');
  await act(async () => { completeProfile({ data: fixture }); });
  expect(screen.getByText('anonymous')).toBeInTheDocument();
  expect(localStorage.getItem('user')).toBeNull();
});
