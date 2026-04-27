import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

function NavIcon({ d }: { d: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

const navItems = [
  { to: '/', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4' },
  { to: '/accounts', label: 'Accounts', icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z' },
  { to: '/scps', label: 'SCPs', icon: 'M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z' },
];

export default function Layout() {
  const { role, signOut } = useAuth();
  const location = useLocation();
  const isControlsActive = location.pathname.startsWith('/controls');

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-title">Governance</div>
        <nav style={{ marginTop: 8 }}>
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              <NavIcon d={item.icon} />
              {item.label}
            </NavLink>
          ))}

          {/* Controls with sub-menu */}
          <NavLink to="/controls/enabled" className={() => `nav-link ${isControlsActive ? 'active' : ''}`}>
            <NavIcon d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            Controls
          </NavLink>
          {isControlsActive && (
            <div className="nav-sub">
              <NavLink to="/controls/enabled" end className={({ isActive }) => `nav-sub-link ${isActive ? 'active' : ''}`}>Enabled</NavLink>
              <NavLink to="/controls/catalog" className={({ isActive }) => `nav-sub-link ${isActive ? 'active' : ''}`}>Catalog</NavLink>
            </div>
          )}

          <NavLink to="/observations" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            <NavIcon d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            Observations
          </NavLink>
          {role === 'administrator' && (
            <NavLink to="/deployments" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              <NavIcon d="M13 10V3L4 14h7v7l9-11h-7z" />
              Deployments
            </NavLink>
          )}
        </nav>
      </aside>
      <div className="main-area">
        <header className="app-header">
          <span style={{ fontWeight: 500 }}>{role === 'administrator' ? '🔑 Administrator' : '👁 Viewer'}</span>
          <button onClick={signOut}>Sign Out</button>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
