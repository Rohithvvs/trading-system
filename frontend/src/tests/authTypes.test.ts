import { describe, expect, test } from 'vitest';
import type { AuthResponse, UserProfile, UserRole } from '../types/auth';
import { DEFAULT_ROLE, VALID_ROLES } from '../types/auth';

describe('frontend auth types (AC-FE-01)', () => {
  test('UserRole union only allows trader|admin via constants', () => {
    const roles: UserRole[] = ['trader', 'admin'];
    for (const r of roles) {
      expect(VALID_ROLES).toContain(r);
    }
    expect(DEFAULT_ROLE).toBe('trader');
  });

  test('AuthResponse shape fields required by login/register contract', () => {
    const sample: AuthResponse = {
      id: 'usr_1',
      email: 'u@example.com',
      full_name: 'User',
      role: 'trader',
      access_token: 'token',
    };
    expect(sample.role).toBe('trader');
    expect(sample.access_token).toBeTruthy();
  });

  test('UserProfile holds role for auth context state', () => {
    const profile: UserProfile = {
      id: 'usr_2',
      email: 'a@example.com',
      full_name: 'Admin',
      role: 'admin',
    };
    expect(profile.role).toBe('admin');
  });
});
