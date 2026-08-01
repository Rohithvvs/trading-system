export type UserRole = 'trader' | 'admin';

export const DEFAULT_ROLE: UserRole = 'trader';
export const VALID_ROLES: UserRole[] = ['trader', 'admin'];

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  profile_picture?: string;
  is_email_verified?: boolean;
}

export interface AuthResponse {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  access_token: string;
  refresh_token?: string;
}
