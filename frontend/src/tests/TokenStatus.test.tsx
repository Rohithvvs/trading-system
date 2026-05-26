import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TokenStatus from '../components/TokenStatus';
import * as api from '../api';

// Mock the API methods
vi.mock('../api', () => ({
  getTokenStatus: vi.fn(),
  getTokenHistory: vi.fn(),
  saveAccessToken: vi.fn(),
}));

describe('TokenStatus Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Default mocks for standard rendering
    vi.mocked(api.getTokenStatus).mockResolvedValue({
      access_token_active: false,
      access_token_saved_at: null,
      status: 'no_token',
      last_error: null,
    });
    
    vi.mocked(api.getTokenHistory).mockResolvedValue({ history: [] });
  });

  it('renders default state without token', async () => {
    render(<TokenStatus />);
    
    expect(screen.getByText('FYERS Access Token')).toBeDefined();
    
    await waitFor(() => {
      expect(screen.getByTestId('token-status-badge').textContent).toBe('No token');
    });

    const input = screen.getByTestId('access-token-input') as HTMLInputElement;
    expect(input.value).toBe('');
    
    const button = screen.getByTestId('save-access-token-button') as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('handles successful token validation and save (Success UI Flow)', async () => {
    vi.mocked(api.saveAccessToken).mockResolvedValue({ status: 'ok', saved_at: '2023-01-01T00:00:00Z' });
    
    render(<TokenStatus />);
    
    const input = screen.getByTestId('access-token-input') as HTMLInputElement;
    const button = screen.getByTestId('save-access-token-button') as HTMLButtonElement;
    
    fireEvent.change(input, { target: { value: 'valid_token' } });
    expect(button.disabled).toBe(false);
    
    fireEvent.click(button);
    
    // Immediate state should be saving - button disabled and text updated
    expect(button.disabled).toBe(true);
    expect(screen.getByText('Validating with broker...')).toBeDefined();
    
    // Wait for success completion banner
    await waitFor(() => {
      const successBox = screen.getByText('Token successfully verified and saved.');
      expect(successBox).toBeDefined();
      expect(successBox.className).toBe('success-box');
    });
    
    // Verify input was cleared
    expect(input.value).toBe('');
  });

  it('handles failed token validation (Error UI Flow)', async () => {
    vi.mocked(api.saveAccessToken).mockRejectedValue(new Error('Invalid or Expired FYERS Token.'));
    
    render(<TokenStatus />);
    
    const input = screen.getByTestId('access-token-input') as HTMLInputElement;
    const button = screen.getByTestId('save-access-token-button') as HTMLButtonElement;
    
    fireEvent.change(input, { target: { value: 'invalid_token' } });
    fireEvent.click(button);
    
    // Wait for error banner
    await waitFor(() => {
      const errorBox = screen.getByText('Invalid or Expired FYERS Token.');
      expect(errorBox).toBeDefined();
      expect(errorBox.className).toBe('error-box');
    });
    
    // Verify success banner is not present
    expect(screen.queryByText('Token successfully verified and saved.')).toBeNull();
  });
});
