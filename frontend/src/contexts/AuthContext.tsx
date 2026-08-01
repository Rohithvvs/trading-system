/**
 * @deprecated Do not use. The live application mounts `hooks/useAuth` AuthProvider
 * from `main.tsx`. This file re-exports the production provider to prevent
 * accidental dual auth stacks (audit M-1).
 */
export { AuthProvider, useAuth } from '../hooks/useAuth';
export type { AuthUser } from '../hooks/useAuth';
