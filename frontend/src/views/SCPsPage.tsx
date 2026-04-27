import { useEffect, useState } from 'react';
import { api } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

interface SCPTarget { target_id: string; target_type: string; target_name: string; }
interface SCP { id: string; name: string; arn: string; description: string; content: Record<string, unknown>; type: string; targets: SCPTarget[]; }

function AttachForm({ scpId, onSuccess }: { scpId: string; onSuccess: () => void }) {
  const [targetId, setTargetId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState<{ text: string; error: boolean } | null>(null);

  const handleAttach = async () => {
    if (!targetId.trim()) return;
    setSubmitting(true); setMsg(null);
    try {
      await api.post('/api/execute', { type: 'attach_scp', parameters: { PolicyId: scpId, TargetId: targetId.trim() } });
      setMsg({ text: 'SCP attached successfully', error: false });
      setTargetId('');
      onSuccess();
    } catch (e: unknown) {
      setMsg({ text: e instanceof Error ? e.message : 'Failed', error: true });
    } finally { setSubmitting(false); }
  };

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginTop: 12, flexWrap: 'wrap' }}>
      <div className="deploy-field" style={{ marginBottom: 0, flex: 1, minWidth: 200 }}>
        <span>Attach to Target</span>
        <input value={targetId} onChange={e => setTargetId(e.target.value)} placeholder="OU ID or Account ID (e.g. ou-xxxx-xxxxxxxx)" />
      </div>
      <button className="btn btn-primary" onClick={handleAttach} disabled={submitting || !targetId.trim()}>
        {submitting ? 'Submitting…' : 'Attach SCP'}
      </button>
      {msg && <span className={msg.error ? 'error-text' : 'deploy-success'} style={{ fontSize: 12 }}>{msg.text}</span>}
    </div>
  );
}

export default function SCPsPage() {
  const { role } = useAuth();
  const isAdmin = role === 'administrator';
  const [scps, setScps] = useState<SCP[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const fetchScps = () => {
    api.get<{ data: SCP[] }>('/api/scps')
      .then(res => setScps(res.data))
      .catch(err => setError(err.message || 'Failed to load SCPs'))
      .finally(() => setLoading(false));
  };

  useEffect(fetchScps, []);

  if (loading) return <div className="muted">Loading SCPs…</div>;
  if (error) return <div className="error-text">Error: {error}</div>;

  const selected = scps.find(s => s.id === selectedId) ?? null;

  const handleDetach = async (policyId: string, targetId: string) => {
    try {
      await api.post('/api/execute', { type: 'detach_scp', parameters: { PolicyId: policyId, TargetId: targetId } });
      alert('SCP detached successfully');
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Failed to submit detach request');
    }
  };

  return (
    <div>
      <h2>Service Control Policies</h2>
      <div className="scp-layout">
        <div className="scp-list-panel">
          {scps.length === 0 ? <p className="muted" style={{ padding: 16 }}>No SCPs found.</p> : (
            <ul className="scp-list">
              {scps.map(s => (
                <li key={s.id} className={`scp-list-item${selectedId === s.id ? ' scp-list-item--selected' : ''}`} onClick={() => setSelectedId(selectedId === s.id ? null : s.id)}>
                  <strong>{s.name}</strong>
                  <span className="scp-list-desc">{s.description || 'No description'}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {selected && (
          <div className="scp-detail-panel">
            <h3 style={{ margin: '0 0 4px' }}>{selected.name}</h3>
            <p className="ou-detail-meta">ID: {selected.id} · ARN: {selected.arn}</p>
            {selected.description && <p style={{ margin: '0 0 16px', fontSize: 13, color: 'var(--text-secondary)' }}>{selected.description}</p>}

            <section className="ou-detail-section">
              <h4>Policy Document</h4>
              <pre className="scp-policy-doc">{JSON.stringify(selected.content, null, 2)}</pre>
            </section>

            <section className="ou-detail-section">
              <h4>Attachment Targets ({selected.targets?.length ?? 0})</h4>
              {!selected.targets?.length ? <p className="muted">No targets attached.</p> : (
                <table className="ou-detail-table">
                  <thead><tr><th>Target Name</th><th>Target ID</th><th>Type</th>{isAdmin && <th>Action</th>}</tr></thead>
                  <tbody>
                    {selected.targets.map(t => (
                      <tr key={t.target_id}>
                        <td>{t.target_name}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{t.target_id}</td>
                        <td>{t.target_type}</td>
                        {isAdmin && (
                          <td>
                            <button className="btn btn-danger" style={{ padding: '3px 10px', fontSize: 11 }} onClick={(e) => { e.stopPropagation(); handleDetach(selected.id, t.target_id); }}>
                              Detach
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {isAdmin && <AttachForm scpId={selected.id} onSuccess={fetchScps} />}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
