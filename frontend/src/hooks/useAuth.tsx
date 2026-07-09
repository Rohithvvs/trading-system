import React, { createContext, useContext, useState, useEffect } from 'react';
import { authMe } from '../api';

interface AuthUser {
  id: string;
  email: string;
  full_name: string;
}

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (user: AuthUser) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Check if there is an active session
    const validateSession = async () => {
      try {
        const userData = await authMe();
        setUser(userData);
        localStorage.setItem('user', JSON.stringify(userData));
      } catch (err) {
        setUser(null);
        localStorage.removeItem('user');
      } finally {
        setIsLoading(false);
      }
    };
    validateSession();
  }, []);

  const login = (userData: AuthUser) => {
    setUser(userData);
    localStorage.setItem('user', JSON.stringify(userData));
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('user');
    // Make an API call to clear the HttpOnly cookies
    fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/auth/logout`, { method: 'POST' }).catch(console.error);
  };

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
