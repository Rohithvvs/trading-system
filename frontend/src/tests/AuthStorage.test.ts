import { describe, expect, test, beforeEach } from 'vitest';
import { authStorage } from '../utils/storage';
import type { UserProfile } from '../types/auth';
import { DEFAULT_ROLE, VALID_ROLES } from '../types/auth';

describe('authStorage role and profile persistence (AC-FE-01/02/03)', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  test('default role is trader when storage empty', () => {
    expect(authStorage.getUserRole()).toBe('trader');
    expect(authStorage.getUserRole()).toBe(DEFAULT_ROLE);
  });

  test('setUserRole persists admin role in sessionStorage', () => {
    authStorage.setUserRole('admin');
    expect(authStorage.getUserRole()).toBe('admin');
    expect(sessionStorage.getItem('auth_user_role')).toBe('admin');
    // Must not leave durable localStorage role (M-5).
    expect(localStorage.getItem('auth_user_role')).toBeNull();
  });

  test('setUserRole persists trader role', () => {
    authStorage.setUserRole('trader');
    expect(authStorage.getUserRole()).toBe('trader');
  });

  test('invalid stored role falls back to trader', () => {
    sessionStorage.setItem('auth_user_role', 'superuser');
    expect(authStorage.getUserRole()).toBe('trader');
  });

  test('setUserProfile persists profile and extracts user.role (AC-FE-01/02)', () => {
    const profile: UserProfile = {
      id: 'usr_999',
      email: 'admin@example.com',
      full_name: 'Admin User',
      role: 'admin',
    };
    authStorage.setUserProfile(profile);

    const stored = authStorage.getUserProfile();
    expect(stored).not.toBeNull();
    expect(stored?.id).toBe('usr_999');
    expect(stored?.email).toBe('admin@example.com');
    expect(stored?.full_name).toBe('Admin User');
    expect(stored?.role).toBe('admin');
    expect(authStorage.getUserRole()).toBe('admin');
  });

  test('setUserProfile with trader role', () => {
    authStorage.setUserProfile({
      id: 'usr_1',
      email: 't@example.com',
      full_name: 'Trader',
      role: 'trader',
    });
    expect(authStorage.getUserProfile()?.role).toBe('trader');
    expect(authStorage.getUserRole()).toBe('trader');
  });

  test('does not store access token in browser storage (audit H-2)', () => {
    authStorage.setAccessToken('jwt.token.value');
    expect(authStorage.getAccessToken()).toBeNull();
    expect(localStorage.getItem('auth_access_token')).toBeNull();
    expect(sessionStorage.getItem('auth_access_token')).toBeNull();
  });

  test('clears legacy access token key on get/set', () => {
    localStorage.setItem('auth_access_token', 'legacy-jwt');
    expect(authStorage.getAccessToken()).toBeNull();
    expect(localStorage.getItem('auth_access_token')).toBeNull();
  });

  test('migrates legacy localStorage profile into sessionStorage', () => {
    localStorage.setItem(
      'auth_user_profile',
      JSON.stringify({
        id: 'legacy',
        email: 'l@example.com',
        full_name: 'Legacy',
        role: 'admin',
      }),
    );
    const profile = authStorage.getUserProfile();
    expect(profile?.role).toBe('admin');
    expect(sessionStorage.getItem('auth_user_profile')).toBeTruthy();
    expect(localStorage.getItem('auth_user_profile')).toBeNull();
  });

  test('clearAuth purges role and profile (logout path)', () => {
    authStorage.setUserRole('admin');
    authStorage.setUserProfile({
      id: 'u',
      email: 'a@example.com',
      full_name: 'A',
      role: 'admin',
    });
    authStorage.clearAuth();
    expect(authStorage.getUserRole()).toBe('trader');
    expect(authStorage.getUserProfile()).toBeNull();
  });

  test('rehydration from storage after clear-reload simulation (AC-FE-03)', () => {
    authStorage.setUserProfile({
      id: 'usr_rehydrate',
      email: 're@example.com',
      full_name: 'Re User',
      role: 'admin',
    });

    expect(authStorage.getUserProfile()?.role).toBe('admin');
    expect(authStorage.getUserRole()).toBe('admin');
  });

  test('profile with invalid role coerces to trader', () => {
    sessionStorage.setItem(
      'auth_user_profile',
      JSON.stringify({
        id: 'x',
        email: 'x@example.com',
        full_name: 'X',
        role: 'root',
      }),
    );
    expect(authStorage.getUserProfile()?.role).toBe('trader');
  });
});

describe('auth types constants', () => {
  test('VALID_ROLES contains only trader and admin', () => {
    expect(VALID_ROLES).toEqual(['trader', 'admin']);
    expect(DEFAULT_ROLE).toBe('trader');
  });
});
