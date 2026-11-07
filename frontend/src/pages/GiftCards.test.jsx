import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import GiftCards from './GiftCards';
import { loadRazorpay } from '../utils/loadRazorpay';
import { AuthContext } from '../context/AuthContext';

jest.mock('../components/AppLayout', () => ({ children }) => <div>{children}</div>);
jest.mock('../utils/loadRazorpay', () => ({ loadRazorpay: jest.fn().mockResolvedValue(true) }));
const axiosInstance = { get: jest.fn(), post: jest.fn() };
const user = { id: 1 };
const renderPage = () => render(<AuthContext.Provider value={{ axiosInstance, user }}><GiftCards /></AuthContext.Provider>);

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  loadRazorpay.mockResolvedValue(true);
  axiosInstance.get.mockResolvedValue({ data: [] });
  window.alert = jest.fn();
  window.Razorpay = jest.fn().mockImplementation(() => ({ open: jest.fn(), on: jest.fn() }));
});

test('recovers a privately issued card after an interrupted response', async () => {
  axiosInstance.get.mockResolvedValue({ data: [{ intent_id: 'intent', state: 'settled', active: true,
    gift_card_id: 'private-fixture', amount: '50.00', qr_url: 'data:image/png;base64,fixture' }] });
  renderPage();
  fireEvent.click(await screen.findByRole('button', { name: /View purchased gift card/ }));
  expect(await screen.findByText(/private-fixture/)).toBeInTheDocument();
  expect(screen.getByAltText('Gift Card QR')).toHaveAttribute('src', 'data:image/png;base64,fixture');
  expect(axiosInstance.post).not.toHaveBeenCalled();
});

test('unknown initialization keeps the same purchase key and reports uncertainty', async () => {
  axiosInstance.post.mockRejectedValue({ response: { data: { error: 'Purchase requires reconciliation.' } } });
  const { container } = renderPage();
  await waitFor(() => expect(axiosInstance.get).toHaveBeenCalled());
  fireEvent.submit(container.querySelector('form'));
  await waitFor(() => expect(window.alert).toHaveBeenCalledWith('Purchase requires reconciliation.'));
  const key = axiosInstance.post.mock.calls[0][1].idempotency_key;
  fireEvent.submit(container.querySelector('form'));
  await waitFor(() => expect(axiosInstance.post).toHaveBeenCalledTimes(2));
  expect(axiosInstance.post.mock.calls[1][1].idempotency_key).toBe(key);
  expect(window.Razorpay).not.toHaveBeenCalled();
});

test('pending purchase recovery never displays an unissued credential', async () => {
  axiosInstance.get.mockResolvedValue({ data: [{ intent_id: 'pending-intent', state: 'reconciliation' }] });
  renderPage();
  expect(await screen.findByText(/pending-intent: reconciliation/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /View purchased gift card/ })).not.toBeInTheDocument();
});

test('confirmed failed attempt releases UI lock but resumes the same purchase key', async () => {
  const handlers = {};
  window.Razorpay.mockImplementation(() => ({ open: jest.fn(), on: (event, fn) => { handlers[event] = fn; } }));
  axiosInstance.post.mockResolvedValue({ data: { order_id: 'order_gift', amount: 50, key: 'fixture' } });
  const { container } = renderPage();
  await waitFor(() => expect(axiosInstance.get).toHaveBeenCalled());
  fireEvent.submit(container.querySelector('form'));
  await waitFor(() => expect(window.Razorpay).toHaveBeenCalledTimes(1));
  const key = axiosInstance.post.mock.calls[0][1].idempotency_key;
  act(() => handlers['payment.failed']());
  fireEvent.submit(container.querySelector('form'));
  await waitFor(() => expect(window.Razorpay).toHaveBeenCalledTimes(2));
  expect(axiosInstance.post.mock.calls[1][1].idempotency_key).toBe(key);
  expect(window.Razorpay.mock.calls[1][0].order_id).toBe('order_gift');
});

test('unknown gift capture is not cleared by a reordered failure or dismissal', async () => {
  const handlers = {};
  window.Razorpay.mockImplementation(() => ({ open: jest.fn(), on: (event, fn) => { handlers[event] = fn; } }));
  axiosInstance.post.mockImplementation(url => url.endsWith('/purchase/')
    ? Promise.resolve({ data: { order_id: 'order_gift', amount: 50, key: 'fixture' } })
    : Promise.reject(new Error('unknown outcome')));
  const { container } = renderPage();
  await waitFor(() => expect(axiosInstance.get).toHaveBeenCalled());
  fireEvent.submit(container.querySelector('form'));
  await waitFor(() => expect(window.Razorpay).toHaveBeenCalledTimes(1));
  const key = axiosInstance.post.mock.calls[0][1].idempotency_key;
  const options = window.Razorpay.mock.calls[0][0];
  await act(async () => {
    await options.handler({ razorpay_payment_id: 'pay_unknown', razorpay_order_id: 'order_gift', razorpay_signature: 'fixture' });
    handlers['payment.failed']();
    options.modal.ondismiss();
  });
  expect(sessionStorage.getItem('eazyshop:purchase:gift_card:1')).toBe(key);
  expect(screen.queryByText('Payment Successful!')).not.toBeInTheDocument();
});

test('a changed denomination conflict preserves the original key and exposes no new checkout', async () => {
  const message = 'This purchase key belongs to a different gift amount. Restore the original request; do not replace this key.';
  axiosInstance.post.mockResolvedValueOnce({ data: { order_id: 'original_gift', amount: 500, key: 'fixture' } })
    .mockRejectedValueOnce({ response: { status: 409, data: { code: 'purchase_request_conflict', error: message } } });
  const { container } = renderPage();
  await waitFor(() => expect(axiosInstance.get).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: '₹500.00' }));
  fireEvent.submit(container.querySelector('form'));
  await waitFor(() => expect(window.Razorpay).toHaveBeenCalledTimes(1));
  const key = axiosInstance.post.mock.calls[0][1].idempotency_key;
  act(() => window.Razorpay.mock.calls[0][0].modal.ondismiss());
  fireEvent.click(screen.getByRole('button', { name: '₹1,000.00' }));
  fireEvent.submit(container.querySelector('form'));
  await waitFor(() => expect(window.alert).toHaveBeenCalledWith(message));
  expect(axiosInstance.post.mock.calls[1][1]).toEqual({ amount: 1000, idempotency_key: key });
  expect(sessionStorage.getItem('eazyshop:purchase:gift_card:1')).toBe(key);
  expect(window.Razorpay).toHaveBeenCalledTimes(1);
  expect(screen.queryByText('Payment Successful!')).not.toBeInTheDocument();
});

test('an identical settled initialization recovers the issued gift without opening the gateway', async () => {
  sessionStorage.setItem('eazyshop:purchase:gift_card:1', 'settled-request');
  axiosInstance.post.mockResolvedValue({ data: {
    payment_complete: true, intent_id: 'settled-intent', order_id: 'original_provider_order',
    gift_card_id: 'original_card', amount: '500.00', active: true, qr_url: 'data:image/png;base64,fixture'
  } });
  const { container } = renderPage();
  await waitFor(() => expect(axiosInstance.get).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: '₹500.00' }));
  fireEvent.submit(container.querySelector('form'));
  expect(await screen.findByText(/original_card/)).toBeInTheDocument();
  expect(axiosInstance.post.mock.calls[0][1].idempotency_key).toBe('settled-request');
  expect(sessionStorage.getItem('eazyshop:purchase:gift_card:1')).toBeNull();
  expect(window.Razorpay).not.toHaveBeenCalled();
});
