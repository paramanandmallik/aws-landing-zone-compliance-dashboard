import { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import LoginPage from './views/LoginPage';
import DashboardPage from './views/DashboardPage';
import AccountsPage from './views/AccountsPage';
import SCPsPage from './views/SCPsPage';
import EnabledControlsPage from './views/EnabledControlsPage';
import ControlCatalogPage from './views/ControlCatalogPage';
import ObservationsPage from './views/ObservationsPage';
import DeploymentsPage from './views/DeploymentsPage';
import { useToast } from './components/Toast';
import { setApiErrorHandler } from './services/api';
import './App.css';

export default function App() {
  const { showToast } = useToast();

  useEffect(() => {
    setApiErrorHandler((status, message) => {
      showToast(`${status}: ${message}`, 'error');
    });
    return () => setApiErrorHandler(null);
  }, [showToast]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/scps" element={<SCPsPage />} />
          <Route path="/controls" element={<Navigate to="/controls/enabled" replace />} />
          <Route path="/controls/enabled" element={<EnabledControlsPage />} />
          <Route path="/controls/catalog" element={<ControlCatalogPage />} />
          <Route path="/observations" element={<ObservationsPage />} />
          <Route path="/deployments" element={<DeploymentsPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
