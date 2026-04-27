import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { CognitoUserSession } from 'amazon-cognito-identity-js';
import * as auth from '../services/auth';

interface AuthState {
  isAuthenticated: boolean;
  role: string;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState>({
  isAuthenticated: false,
  role: 'viewer',
  loading: true,
  signIn: async () => {},
  signOut: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [role, setRole] = useState('viewer');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    auth.getSession().then(async (session) => {
      if (session?.isValid()) {
        setIsAuthenticated(true);
        setRole(await auth.getRole());
      }
      setLoading(false);
    });
  }, []);

  const handleSignIn = useCallback(async (email: string, password: string) => {
    await auth.signIn(email, password);
    setIsAuthenticated(true);
    setRole(await auth.getRole());
  }, []);

  const handleSignOut = useCallback(() => {
    auth.signOut();
    setIsAuthenticated(false);
    setRole('viewer');
  }, []);

  return (
    <AuthContext.Provider
      value={{ isAuthenticated, role, loading, signIn: handleSignIn, signOut: handleSignOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
