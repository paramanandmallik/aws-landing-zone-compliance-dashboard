import { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { OUNode } from './OUTree';

interface AccountItem {
  id: string;
  name: string;
  email: string;
  status: string;
  ou_path: string;
}

interface SCPItem {
  id: string;
  name: string;
  description: string;
  targets: { target_id: string; target_type: string; target_name: string }[];
}

interface ControlItem {
  control_identifier: string;
  status: string;
  ou_id: string;
  ou_name: string;
  drift_status: string | null;
}

interface OUDetailProps {
  ou: OUNode;
}

export default function OUDetail({ ou }: OUDetailProps) {
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [scps, setScps] = useState<SCPItem[]>([]);
  const [controls, setControls] = useState<ControlItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get<{ data: AccountItem[] }>(`/api/accounts?ou_path=${encodeURIComponent(ou.path)}`),
      api.get<{ data: SCPItem[] }>('/api/scps'),
      api.get<{ data: ControlItem[] }>('/api/controls'),
    ]).then(([accRes, scpRes, ctrlRes]) => {
      setAccounts(accRes.data);
      // Filter SCPs that target this OU
      setScps(scpRes.data.filter((scp) =>
        scp.targets?.some((t) => t.target_id === ou.id)
      ));
      // Filter controls enabled on this OU
      setControls(ctrlRes.data.filter((c) => c.ou_id === ou.id));
    }).catch(() => {
      setAccounts([]);
      setScps([]);
      setControls([]);
    }).finally(() => setLoading(false));
  }, [ou.id, ou.path]);

  if (loading) return <div className="ou-detail-panel"><p>Loading details…</p></div>;

  return (
    <div className="ou-detail-panel">
      <h3 style={{ margin: '0 0 4px' }}>{ou.name}</h3>
      <p className="ou-detail-meta">ID: {ou.id} &middot; Path: {ou.path}</p>

      <section className="ou-detail-section">
        <h4>Accounts ({accounts.length})</h4>
        {accounts.length === 0 ? <p className="muted">No accounts in this OU.</p> : (
          <table className="ou-detail-table">
            <thead><tr><th>Name</th><th>ID</th><th>Status</th><th>Email</th></tr></thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id}><td>{a.name}</td><td>{a.id}</td><td>{a.status}</td><td>{a.email}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="ou-detail-section">
        <h4>Attached SCPs ({scps.length})</h4>
        {scps.length === 0 ? <p className="muted">No SCPs attached to this OU.</p> : (
          <ul className="ou-detail-list">
            {scps.map((s) => <li key={s.id}><strong>{s.name}</strong> — {s.description || 'No description'}</li>)}
          </ul>
        )}
      </section>

      <section className="ou-detail-section">
        <h4>Enabled Controls ({controls.length})</h4>
        {controls.length === 0 ? <p className="muted">No controls enabled on this OU.</p> : (
          <ul className="ou-detail-list">
            {controls.map((c) => (
              <li key={c.control_identifier}>
                {c.control_identifier} — <span className={`status-${c.status.toLowerCase()}`}>{c.status}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
