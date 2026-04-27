import { useEffect, useState } from 'react';
import { api } from '../services/api';

interface Account {
  id: string;
  name: string;
  email: string;
  status: string;
  arn: string;
  ou_id: string;
  ou_path: string;
  joined_timestamp: string;
}

interface SCPItem { id: string; name: string; description: string; targets: { target_id: string }[]; }
interface ControlItem { control_identifier: string; status: string; ou_id: string; ou_name: string; drift_status: string | null; }

const STATUS_OPTIONS = ['All', 'ACTIVE', 'SUSPENDED', 'PENDING_CLOSURE'];

function AccountDetail({ account, scps, controls }: { account: Account; scps: SCPItem[]; controls: ControlItem[] }) {
  // SCPs attached to this account's OU or directly
  const relevantScps = scps.filter(s => s.targets?.some(t => t.target_id === account.ou_id || t.target_id === account.id));
  const relevantControls = controls.filter(c => c.ou_id === account.ou_id);

  return (
    <div className="account-detail-content">
      <div className="account-detail-section">
        <h4>SCPs ({relevantScps.length})</h4>
        {relevantScps.length === 0 ? <p className="muted">No SCPs apply to this account.</p> : (
          <ul className="ou-detail-list">
            {relevantScps.map(s => <li key={s.id}><strong>{s.name}</strong> — {s.description || 'No description'}</li>)}
          </ul>
        )}
      </div>
      <div className="account-detail-section">
        <h4>Controls ({relevantControls.length})</h4>
        {relevantControls.length === 0 ? <p className="muted">No controls on this account's OU.</p> : (
          <ul className="ou-detail-list">
            {relevantControls.map(c => (
              <li key={c.control_identifier}>
                {c.control_identifier} — <span className={`status-${c.status.toLowerCase()}`}>{c.status}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [scps, setScps] = useState<SCPItem[]>([]);
  const [controls, setControls] = useState<ControlItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('All');
  const [ouFilter, setOuFilter] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.get<{ data: Account[] }>('/api/accounts'),
      api.get<{ data: SCPItem[] }>('/api/scps'),
      api.get<{ data: ControlItem[] }>('/api/controls'),
    ]).then(([accRes, scpRes, ctrlRes]) => {
      setAccounts(accRes.data);
      setScps(scpRes.data);
      setControls(ctrlRes.data);
    }).catch(err => setError(err.message || 'Failed to load data'))
      .finally(() => setLoading(false));
  }, []);

  const filtered = accounts.filter(a => {
    if (statusFilter !== 'All' && a.status !== statusFilter) return false;
    if (ouFilter && !a.ou_path.toLowerCase().includes(ouFilter.toLowerCase())) return false;
    if (search) {
      const s = search.toLowerCase();
      if (!a.name.toLowerCase().includes(s) && !a.email.toLowerCase().includes(s) && !a.id.toLowerCase().includes(s)) return false;
    }
    return true;
  });

  if (loading) return <div className="muted">Loading accounts…</div>;
  if (error) return <div className="error-text">Error: {error}</div>;

  return (
    <div>
      <h2>Accounts</h2>
      <div className="accounts-filters">
        <input type="text" placeholder="Search by name, email, or ID" value={search} onChange={e => setSearch(e.target.value)} className="accounts-search" />
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="accounts-select">
          {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <input type="text" placeholder="Filter by OU path" value={ouFilter} onChange={e => setOuFilter(e.target.value)} className="accounts-search" />
      </div>
      <table className="accounts-table">
        <thead>
          <tr><th>Name</th><th>Account ID</th><th>OU Path</th><th>Status</th><th>Email</th></tr>
        </thead>
        <tbody>
          {filtered.length === 0 ? (
            <tr><td colSpan={5} className="muted">No accounts match the current filters.</td></tr>
          ) : filtered.map(a => (
            <>
              <tr key={a.id} className={expandedId === a.id ? 'account-row--selected' : ''} onClick={() => setExpandedId(expandedId === a.id ? null : a.id)}>
                <td>{a.name}</td>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{a.id}</td>
                <td>{a.ou_path || '—'}</td>
                <td><span className={`status-badge status-badge--${a.status.toLowerCase()}`}>{a.status}</span></td>
                <td>{a.email}</td>
              </tr>
              {expandedId === a.id && (
                <tr key={`${a.id}-detail`} className="account-detail-row">
                  <td colSpan={5}><AccountDetail account={a} scps={scps} controls={controls} /></td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}
