import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { api } from '../services/api';

interface EnabledControl { control_identifier: string; status: string; ou_id: string; ou_name: string; drift_status: string | null; }

export default function EnabledControlsPage() {
  const [controls, setControls] = useState<EnabledControl[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ data: EnabledControl[] }>('/api/controls')
      .then(res => setControls(res.data))
      .catch(err => setError(err.message || 'Failed'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h2>Control Tower Controls</h2>
      <div className="tab-bar">
        <NavLink to="/controls/enabled" className="tab-btn tab-btn--active">Enabled ({controls.length})</NavLink>
        <NavLink to="/controls/catalog" className="tab-btn">Catalog</NavLink>
      </div>
      {loading ? <div className="muted" style={{ marginTop: 16 }}>Loading…</div> :
       error ? <div className="error-text" style={{ marginTop: 16 }}>{error}</div> : (
        <table className="accounts-table" style={{ marginTop: 16 }}>
          <thead><tr><th>Control</th><th>Status</th><th>OU</th><th>Drift</th></tr></thead>
          <tbody>
            {controls.length === 0 ? <tr><td colSpan={4} className="muted">No enabled controls.</td></tr> :
              controls.map((c, i) => (
                <tr key={`${c.control_identifier}-${c.ou_id}-${i}`}>
                  <td style={{ fontFamily: 'monospace', fontSize: 11, maxWidth: 400, wordBreak: 'break-all' }}>{c.control_identifier}</td>
                  <td><span className={`status-badge status-badge--${c.status.toLowerCase()}`}>{c.status}</span></td>
                  <td>{c.ou_name || c.ou_id}</td>
                  <td>{c.drift_status ?? '—'}</td>
                </tr>
              ))
            }
          </tbody>
        </table>
      )}
    </div>
  );
}
