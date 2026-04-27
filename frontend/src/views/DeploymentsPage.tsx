import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';

type DeploymentType =
  | 'enable_control'
  | 'disable_control'
  | 'create_scp'
  | 'update_scp'
  | 'attach_scp'
  | 'detach_scp';

interface DeploymentRecord {
  id: string;
  type: string;
  parameters: Record<string, unknown>;
  status: string;
  requested_by: string;
  requested_at: string;
  approved_by?: string | null;
  approved_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

const DEPLOYMENT_TYPES: { value: DeploymentType; label: string }[] = [
  { value: 'enable_control', label: 'Enable Control' },
  { value: 'disable_control', label: 'Disable Control' },
  { value: 'create_scp', label: 'Create SCP' },
  { value: 'update_scp', label: 'Update SCP' },
  { value: 'attach_scp', label: 'Attach SCP' },
  { value: 'detach_scp', label: 'Detach SCP' },
];

const STATUS_COLORS: Record<string, string> = {
  pending: '#e65100',
  approved: '#1565c0',
  completed: '#2e7d32',
  failed: '#c62828',
  rejected: '#757575',
  executing: '#1565c0',
};

function truncateId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) + '…' : id;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function DeploymentForm({ onSuccess }: { onSuccess: () => void }) {
  const [type, setType] = useState<DeploymentType>('enable_control');
  const [params, setParams] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);

  const updateParam = (key: string, value: string) =>
    setParams((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);

    let parameters: Record<string, unknown> = { ...params };
    if (type === 'create_scp' || type === 'update_scp') {
      try {
        if (params.Content) {
          parameters = { ...parameters, Content: JSON.parse(params.Content) };
        }
      } catch {
        setMessage({ text: 'Content must be valid JSON', error: true });
        setSubmitting(false);
        return;
      }
    }

    try {
      await api.post('/api/deployments', { type, parameters });
      setMessage({ text: 'Deployment request submitted successfully', error: false });
      setParams({});
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Submission failed';
      setMessage({ text: msg, error: true });
    } finally {
      setSubmitting(false);
    }
  };

  const renderFields = () => {
    switch (type) {
      case 'enable_control':
      case 'disable_control':
        return (
          <>
            <label className="deploy-field">
              <span>Control Identifier</span>
              <input
                value={params.controlIdentifier ?? ''}
                onChange={(e) => updateParam('controlIdentifier', e.target.value)}
                placeholder="arn:aws:controltower:…"
                required
              />
            </label>
            <label className="deploy-field">
              <span>Target Identifier (OU ARN)</span>
              <input
                value={params.targetIdentifier ?? ''}
                onChange={(e) => updateParam('targetIdentifier', e.target.value)}
                placeholder="arn:aws:organizations:…/ou-…"
                required
              />
            </label>
          </>
        );
      case 'create_scp':
        return (
          <>
            <label className="deploy-field">
              <span>Name</span>
              <input
                value={params.Name ?? ''}
                onChange={(e) => updateParam('Name', e.target.value)}
                required
              />
            </label>
            <label className="deploy-field">
              <span>Description</span>
              <input
                value={params.Description ?? ''}
                onChange={(e) => updateParam('Description', e.target.value)}
              />
            </label>
            <label className="deploy-field">
              <span>Content (JSON)</span>
              <textarea
                className="deploy-textarea"
                value={params.Content ?? ''}
                onChange={(e) => updateParam('Content', e.target.value)}
                placeholder='{"Version":"2012-10-17","Statement":[...]}'
                rows={6}
                required
              />
            </label>
          </>
        );
      case 'update_scp':
        return (
          <>
            <label className="deploy-field">
              <span>Policy ID</span>
              <input
                value={params.PolicyId ?? ''}
                onChange={(e) => updateParam('PolicyId', e.target.value)}
                placeholder="p-xxxxxxxxxx"
                required
              />
            </label>
            <label className="deploy-field">
              <span>Content (JSON)</span>
              <textarea
                className="deploy-textarea"
                value={params.Content ?? ''}
                onChange={(e) => updateParam('Content', e.target.value)}
                placeholder='{"Version":"2012-10-17","Statement":[...]}'
                rows={6}
                required
              />
            </label>
          </>
        );
      case 'attach_scp':
      case 'detach_scp':
        return (
          <>
            <label className="deploy-field">
              <span>Policy ID</span>
              <input
                value={params.PolicyId ?? ''}
                onChange={(e) => updateParam('PolicyId', e.target.value)}
                placeholder="p-xxxxxxxxxx"
                required
              />
            </label>
            <label className="deploy-field">
              <span>Target ID</span>
              <input
                value={params.TargetId ?? ''}
                onChange={(e) => updateParam('TargetId', e.target.value)}
                placeholder="ou-xxxx-xxxxxxxx or account ID"
                required
              />
            </label>
          </>
        );
    }
  };

  return (
    <form className="deploy-form" onSubmit={handleSubmit}>
      <h3>New Deployment Request</h3>
      <label className="deploy-field">
        <span>Deployment Type</span>
        <select
          value={type}
          onChange={(e) => {
            setType(e.target.value as DeploymentType);
            setParams({});
            setMessage(null);
          }}
        >
          {DEPLOYMENT_TYPES.map((dt) => (
            <option key={dt.value} value={dt.value}>{dt.label}</option>
          ))}
        </select>
      </label>
      {renderFields()}
      {message && (
        <p className={message.error ? 'error-text' : 'deploy-success'}>{message.text}</p>
      )}
      <button type="submit" className="deploy-submit" disabled={submitting}>
        {submitting ? 'Submitting…' : 'Submit Request'}
      </button>
    </form>
  );
}

function DeploymentTable() {
  const [deployments, setDeployments] = useState<DeploymentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchDeployments = useCallback(async () => {
    try {
      const res = await api.get<{ data: DeploymentRecord[] }>('/api/deployments');
      setDeployments(res.data);
      setError('');
    } catch {
      setError('Failed to load deployments');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDeployments();
    const interval = setInterval(fetchDeployments, 30_000);
    return () => clearInterval(interval);
  }, [fetchDeployments]);

  if (loading) return <p className="muted">Loading deployments…</p>;
  if (error) return <p className="error-text">{error}</p>;
  if (!deployments.length) return <p className="muted">No deployment requests yet.</p>;

  return (
    <table className="deploy-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Type</th>
          <th>Status</th>
          <th>Requested By</th>
          <th>Requested At</th>
        </tr>
      </thead>
      <tbody>
        {deployments.map((d) => (
          <tr key={d.id}>
            <td title={d.id}>{truncateId(d.id)}</td>
            <td>{d.type.replace(/_/g, ' ')}</td>
            <td>
              <span
                className="deploy-status-badge"
                style={{ background: STATUS_COLORS[d.status] ?? '#999', color: '#fff' }}
              >
                {d.status}
              </span>
            </td>
            <td>{d.requested_by}</td>
            <td>{formatDate(d.requested_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function DeploymentsPage() {
  const { role } = useAuth();
  const [refreshKey, setRefreshKey] = useState(0);

  if (role !== 'administrator') {
    return (
      <div>
        <h2>Deployments</h2>
        <p className="error-text">Access denied. Administrator role required.</p>
      </div>
    );
  }

  return (
    <div>
      <h2>Deployments</h2>
      <DeploymentForm onSuccess={() => setRefreshKey((k) => k + 1)} />
      <h3 style={{ marginTop: 24 }}>Deployment Status</h3>
      <DeploymentTable key={refreshKey} />
    </div>
  );
}
