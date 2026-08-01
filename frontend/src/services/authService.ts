/**
 * @deprecated Use `api.ts` (`authLogin`, `authSignup`, `authMe`) + `hooks/useAuth`.
 * Thin re-exports kept so accidental imports do not revive a parallel auth stack.
 */
export {
  authLogin as login,
  authSignup as register,
  authMe as getCurrentUser,
  authLogout as logout,
} from '../api';

import { authLogin, authSignup, authMe, authLogout } from '../api';

/** @deprecated Prefer named exports from `../api`. */
export const authService = {
  login: authLogin,
  register: authSignup,
  getCurrentUser: authMe,
  logout: authLogout,
};
