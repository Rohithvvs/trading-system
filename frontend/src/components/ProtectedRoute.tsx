import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

/**
 * Auth gate that never freezes on a blank spinner when a cached session exists.
 * - Cached user → render children immediately (revalidation is background)
 * - No user + loading → lightweight shell (not full-page wait forever)
 * - No user + done → redirect login
 */
export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  // Instant path: authenticated (from cache or network)
  if (isAuthenticated) {
    return <>{children}</>;
  }

  // Only block when we have zero session info and still checking
  if (isLoading) {
    return (
      <div
        className="flex h-screen w-full flex-col items-center justify-center gap-3"
        style={{ background: "var(--bg, #0e1116)", color: "var(--text-muted, #9eacbb)" }}
        role="status"
        aria-live="polite"
      >
        <div
          className="app-skel"
          style={{ width: 48, height: 48, borderRadius: "50%" }}
          aria-hidden
        />
        <div className="app-skel" style={{ width: 160, height: 12, borderRadius: 6 }} aria-hidden />
        <span style={{ fontSize: 13, opacity: 0.8 }}>Restoring session…</span>
      </div>
    );
  }

  return <Navigate to="/login" state={{ from: location }} replace />;
};
