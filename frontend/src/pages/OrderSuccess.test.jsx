import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import OrderSuccess from './OrderSuccess';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

describe('OrderSuccess Component', () => {
  it('renders order details correctly from router state', () => {
    // We mock the exact state that Checkout.jsx sends to this page
    const mockState = {
      order: { total_price: '500.00' },
      payment: { payment_method: 'credit_card', transaction_id: 'txn_12345' },
      userAddress: '123 Testing Lane',
      userPhone: '(555) 123-4567'
    };

    render(
      <MemoryRouter initialEntries={[{ pathname: '/order-success/999', state: mockState }]}>
        <Routes>
          <Route path="/order-success/:orderId" element={<OrderSuccess />} />
        </Routes>
      </MemoryRouter>
    );

    // Assert that the page successfully parsed the state
    expect(screen.getByText('Payment Successful!')).toBeInTheDocument();
    expect(screen.getByText('#999')).toBeInTheDocument();
    expect(screen.getByText('txn_12345')).toBeInTheDocument();
    expect(screen.getByText('123 Testing Lane')).toBeInTheDocument();
    expect(screen.getByText('₹500.00')).toBeInTheDocument();
  });
});