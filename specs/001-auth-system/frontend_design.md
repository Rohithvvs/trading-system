# Frontend Design

## Architecture & State Management
- **Framework**: React 18 with Vite.
- **Styling**: Tailwind CSS, consistent with the existing layout and the premium trading theme (referencing `LOGIN_PAGE_VIEW.png`).
- **State Management**: React Context (`AuthContext`) for global session state (user info, token presence, roles).
- **Routing**: `react-router-dom` v7. Protected routes will be wrapped in a `<ProtectedRoute>` component.

## Components

### Reusable UI Components
- `AuthLayout`: Wraps all auth pages with the premium background, split pane (image left, form right), and branding.
- `AuthCard`: The glassmorphic container for the form.
- `AuthInput`: Reusable text/email input with floating labels, focus animations, and inline error states.
- `PasswordInput`: Extends `AuthInput` with a toggle visibility button and a `PasswordStrengthMeter` below it.
- `AuthButton`: Primary submit button with loading spinner state and gradient styles.
- `PinPad`: A numeric keypad component specifically designed for entering the 4-digit PIN (important for mobile UX).
- `ToastNotification`: Reusable alert for success/error messages, replacing raw JSON outputs.

### Pages

#### 1. Login Page (`/login`)
- **Visuals**: Matches `LOGIN_PAGE_VIEW.png` perfectly.
- **Elements**: Email, Password (with toggle), "Remember Me", "Forgot Password", "Sign In" button, "Create Account" link.
- **Flow**: Submits credentials -> If success -> Redirects to Dashboard (or MFA step if enabled).

#### 2. Signup Page (`/signup`)
- **Visuals**: Identical design language to Login.
- **Elements**: Full Name, Email, Password, Confirm Password.
- **Validation**: Strict client-side validation reflecting the 8 rules (min 12 chars, upper, lower, etc.) updating the UI in real-time.

#### 3. Create PIN Page (`/setup-pin`)
- **Visuals**: Minimalist card centered on screen.
- **Elements**: 4 empty circles for PIN entry, a numeric keypad below.
- **Validation**: Rejects 1234, 0000, birth years.

#### 4. Session Management Page (`/settings/sessions`)
- **Elements**: List of active sessions mapped over `SessionCard` components. Highlights the "Current Session". Includes a "Revoke" button per non-current session and a global "Revoke All" button.

## Hooks & Context

- `useAuth()`: Hook to access the `AuthContext`. Provides `login(email, pass)`, `logout()`, `user` object, and `isAuthenticated` boolean.
- `useRequireAuth(role?)`: Hook used inside protected routes to redirect unauthenticated users to `/login`.

## Security Implementations
- **Token Storage**: Access tokens kept in memory (or HttpOnly cookies if backend is configured for it).
- **Error Handling**: All generic backend `401` or `400` errors are caught by an Axios interceptor and translated to user-friendly Toast messages (e.g., "Invalid credentials", never `{"detail": "..."}`).
