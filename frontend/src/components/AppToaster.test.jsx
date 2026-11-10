import { render } from '@testing-library/react';
import '@testing-library/jest-dom';
import AppToaster from './AppToaster';
import { useToasterStore, toast } from 'react-hot-toast';

jest.mock('react-hot-toast', () => {
  return {
    Toaster: () => <div data-testid="toaster-root" />,
    useToasterStore: jest.fn(),
    toast: {
      dismiss: jest.fn(),
    },
  };
});

describe('AppToaster Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the toaster container without errors', () => {
    useToasterStore.mockReturnValue({ toasts: [] });
    const { getByTestId } = render(<AppToaster />);
    expect(getByTestId('toaster-root')).toBeInTheDocument();
    expect(toast.dismiss).not.toHaveBeenCalled();
  });

  it('does not dismiss when visible toast count is within limit of 1', () => {
    useToasterStore.mockReturnValue({
      toasts: [{ id: 'toast-1', visible: true }],
    });

    render(<AppToaster />);
    expect(toast.dismiss).not.toHaveBeenCalled();
  });

  it('dismisses older toasts exceeding TOAST_LIMIT when multiple visible toasts exist', () => {
    useToasterStore.mockReturnValue({
      toasts: [
        { id: 'toast-1', visible: true },
        { id: 'toast-2', visible: true },
        { id: 'toast-3', visible: true },
      ],
    });

    render(<AppToaster />);
    expect(toast.dismiss).toHaveBeenCalledTimes(2);
    expect(toast.dismiss).toHaveBeenCalledWith('toast-2');
    expect(toast.dismiss).toHaveBeenCalledWith('toast-3');
    expect(toast.dismiss).not.toHaveBeenCalledWith('toast-1');
  });

  it('ignores invisible toasts when computing the toast limit', () => {
    useToasterStore.mockReturnValue({
      toasts: [
        { id: 'toast-1', visible: false },
        { id: 'toast-2', visible: true },
      ],
    });

    render(<AppToaster />);
    // Only one visible toast ('toast-2'), so nothing should be dismissed
    expect(toast.dismiss).not.toHaveBeenCalled();
  });
});
