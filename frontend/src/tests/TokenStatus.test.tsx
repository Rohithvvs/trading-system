import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TokenStatus from '../components/TokenStatus';
import * as api from '../api';

vi.mock('../api', () => ({
  getTokenStatus: vi.fn(),
  getTokenHistory: vi.fn(),
  getFyersAuthUrl: vi.fn(),
  getLatestScan: vi.fn(),
  fetchBrokerToken: vi.fn(),
  saveBrokerToken: vi.fn(),
  updateBrokerToken: vi.fn(),
  deleteBrokerToken: vi.fn(),
  validateBrokerToken: vi.fn(),
  testBrokerConnection: vi.fn(),
  saveAccessToken: vi.fn(),
}));

describe('TokenStatus Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getTokenStatus).mockResolvedValue({
      access_token_active: false,
      access_token_saved_at: null,
      status: 'no_token',
      last_error: null,
    });
    vi.mocked(api.getTokenHistory).mockResolvedValue({ history: [] });
    vi.mocked(api.getLatestScan).mockResolvedValue(null as any);
    vi.mocked(api.fetchBrokerToken).mockResolvedValue({
      exists: false,
      broker: 'FYERS',
      connection_status: 'Disconnected',
    });
  });

  it('renders default state without token', async () => {
    render(<TokenStatus />);

    expect(screen.getByText('Token Management')).toBeDefined();

    await waitFor(() => {
      const badge = screen.getByTestId('token-status-badge');
      expect(badge.textContent).toMatch(/Disconnected/i);
    });

    const input = screen.getByTestId('access-token-input') as HTMLInputElement;
    expect(input.value).toBe('');

    const button = screen.getByTestId('save-access-token-button') as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('handles successful token validation and save (Success UI Flow)', async () => {
    vi.mocked(api.saveBrokerToken).mockResolvedValue({
      status: 'ok',
      message: 'Token successfully verified and saved.',
      token: { token_masked: '************************ABCD', connection_status: 'Connected' },
    });

    render(<TokenStatus />);

    const input = screen.getByTestId('access-token-input') as HTMLInputElement;
    const button = screen.getByTestId('save-access-token-button') as HTMLButtonElement;

    fireEvent.change(input, { target: { value: 'valid_token_long_enough' } });
    expect(button.disabled).toBe(false);

    fireEvent.click(button);

    expect(button.disabled).toBe(true);

    // After the busy state resolves
    await waitFor(() => {
      expect(screen.getByText('Token successfully verified and saved.')).toBeDefined();
    });
  });

  it('handles failed token validation (Error UI Flow)', async () => {
    vi.mocked(api.saveBrokerToken).mockRejectedValue(new Error('Invalid or Expired FYERS Token.'));

    render(<TokenStatus />);

    const input = screen.getByTestId('access-token-input') as HTMLInputElement;
    const button = screen.getByTestId('save-access-token-button') as HTMLButtonElement;

    fireEvent.change(input, { target: { value: 'invalid_token_long' } });
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText('Invalid or Expired FYERS Token.')).toBeDefined();
    });

    expect(screen.queryByText('Token successfully verified and saved.')).toBeNull();
  });
});
