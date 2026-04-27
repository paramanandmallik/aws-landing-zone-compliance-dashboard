import { useEffect, useState, useMemo } from 'react';
import { NavLink } from 'react-router-dom';
import { api } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

interface EnabledControl { control_identifier: string; }
interface AvailableControl { arn: string; name: string; description: string; behavior: string; severity: string; implementation_type: string; implementation_id: string; service: string; governed_resources: string; }
interface OUNode { id: string; name: string; arn: string; path: string; children: OUNode[]; }

const SEV_COLORS: Record<string, string> = { CRITICAL: '#ef4444', HIGH: '#f59e0b', MEDIUM: '#3b82f6', LOW: '#64748b' };

const USE_CASE_RULES: [string[], string][] = [
  [['encrypt', 'kms', 'key management', 'ssl', 'tls', 'certificate', 'secret'], 'Data Protection'],
  [['backup', 'recovery', 'retention', 'snapshot', 'disaster', 'replication'], 'Business Continuity'],
  [['iam', 'access', 'password', 'mfa', 'authentication', 'credential', 'role', 'policy', 'permission', 'root user', 'identity'], 'Identity & Access'],
  [['log', 'trail', 'cloudtrail', 'cloudwatch', 'monitor', 'metric', 'alarm', 'audit'], 'Logging & Monitoring'],
  [['vpc', 'subnet', 'security group', 'network', 'firewall', 'waf', 'elb', 'load balancer', 'route', 'gateway', 'port', 'ssh', 'rdp'], 'Network Security'],
  [['config', 'compliance', 'governance', 'tag', 'guardrail'], 'Governance & Compliance'],
  [['s3', 'bucket', 'public access', 'object'], 'Storage Security'],
  [['rds', 'database', 'dynamodb', 'redshift', 'aurora', 'elasticsearch', 'opensearch'], 'Database Security'],
  [['ec2', 'instance', 'ebs', 'volume', 'ami', 'autoscaling'], 'Compute Security'],
  [['lambda', 'codebuild', 'codepipeline', 'codecommit', 'deploy', 'cicd', 'pipeline'], 'DevOps & Serverless'],
  [['container', 'ecs', 'eks', 'ecr', 'docker', 'fargate', 'kubernetes'], 'Container Security'],
  [['guardduty', 'securityhub', 'detective', 'inspector', 'macie', 'threat', 'vulnerability', 'finding'], 'Threat Detection'],
  [['sagemaker', 'bedrock', 'ai', 'ml', 'machine learning'], 'AI/ML Security'],
];

function deriveUseCase(c: AvailableControl): string {
  const text = `${c.name} ${c.description} ${c.implementation_id || ''} ${c.governed_resources || ''}`.toLowerCase();
  for (const [keywords, useCase] of USE_CASE_RULES) {
    if (keywords.some(k => text.includes(k))) return useCase;
  }
  return 'General';
}

function flattenOUs(nodes: OUNode[], result: { id: string; name: string; path: string; arn: string }[] = []) {
  for (const n of nodes) {
    result.push({ id: n.id, name: n.name, path: n.path, arn: n.arn });
    if (n.children?.length) flattenOUs(n.children, result);
  }
  return result;
}

function EnableControlModal({ controlArn, controlName, ous, onClose, onSuccess }: {
  controlArn: string; controlName: string;
  ous: { id: string; name: string; path: string; arn: string }[];
  onClose: () => void; onSuccess: () => void;
}) {
  const [selectedOu, setSelectedOu] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState<{ text: string; error: boolean } | null>(null);

  const handleEnable = async () => {
    if (!selectedOu) return;
    setSubmitting(true); setMsg(null);
    try {
      const ou = ous.find(o => o.id === selectedOu);
      await api.post('/api/execute', { type: 'enable_control', parameters: { controlIdentifier: controlArn, targetIdentifier: ou?.arn || selectedOu } });
      setMsg({ text: 'Control enabled successfully', error: false });
      onSuccess();
    } catch (e: unknown) { setMsg({ text: e instanceof Error ? e.message : 'Failed', error: true }); }
    finally { setSubmitting(false); }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <h3 style={{ marginBottom: 8 }}>Enable Control</h3>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 4 }}>{controlName}</p>
        <p style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'monospace', wordBreak: 'break-all', marginBottom: 16 }}>{controlArn}</p>
        <label className="deploy-field">
          <span>Target Organizational Unit</span>
          <select value={selectedOu} onChange={e => setSelectedOu(e.target.value)} className="accounts-select" style={{ width: '100%' }}>
            <option value="">Select an OU…</option>
            {ous.map(ou => <option key={ou.id} value={ou.id}>{ou.path || ou.name} ({ou.id})</option>)}
          </select>
        </label>
        {msg && <p className={msg.error ? 'error-text' : 'deploy-success'} style={{ margin: '8px 0' }}>{msg.text}</p>}
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button className="btn btn-primary" onClick={handleEnable} disabled={submitting || !selectedOu}>{submitting ? 'Enabling…' : 'Enable'}</button>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export default function ControlCatalogPage() {
  const { role } = useAuth();
  const isAdmin = role === 'administrator';
  const [catalog, setCatalog] = useState<AvailableControl[]>([]);
  const [enabled, setEnabled] = useState<EnabledControl[]>([]);
  const [ous, setOus] = useState<{ id: string; name: string; path: string; arn: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [sevFilter, setSevFilter] = useState('All');
  const [behaviorFilter, setBehaviorFilter] = useState('All');
  const [serviceFilter, setServiceFilter] = useState('All');
  const [useCaseFilter, setUseCaseFilter] = useState('All');
  const [enableCtrl, setEnableCtrl] = useState<{ arn: string; name: string } | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = (forceRefresh = false) => {
    setLoading(true);
    // Try localStorage cache for catalog (it's 1200+ items, changes rarely)
    const cacheKey = 'gov_control_catalog';
    const cacheTimeKey = 'gov_control_catalog_ts';
    const cached = !forceRefresh ? localStorage.getItem(cacheKey) : null;
    const cachedTs = !forceRefresh ? localStorage.getItem(cacheTimeKey) : null;
    const cacheValid = cached && cachedTs && (Date.now() - Number(cachedTs)) < 3600000; // 1 hour

    const catalogPromise = cacheValid
      ? Promise.resolve({ data: JSON.parse(cached!) as AvailableControl[] })
      : api.get<{ data: AvailableControl[] }>('/api/available-controls').then(res => {
          try { localStorage.setItem(cacheKey, JSON.stringify(res.data)); localStorage.setItem(cacheTimeKey, String(Date.now())); } catch { /* quota */ }
          return res;
        });

    Promise.all([
      catalogPromise,
      api.get<{ data: EnabledControl[] }>('/api/controls'),
      api.get<{ data: OUNode[] }>('/api/ous'),
    ]).then(([avRes, enRes, ouRes]) => {
      setCatalog(avRes.data);
      setEnabled(enRes.data);
      setOus(flattenOUs(ouRes.data));
    }).catch(err => setError(err.message || 'Failed'))
      .finally(() => setLoading(false));
  };

  useEffect(fetchData, []);

  const enabledArns = new Set(enabled.map(c => c.control_identifier));

  const services = useMemo(() => ['All', ...Array.from(new Set(catalog.map(c => c.service || 'General'))).sort()], [catalog]);
  const useCases = useMemo(() => ['All', ...Array.from(new Set(catalog.map(c => deriveUseCase(c)))).sort()], [catalog]);
  const severities = ['All', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
  const behaviors = ['All', 'PREVENTIVE', 'DETECTIVE', 'PROACTIVE'];

  const filtered = catalog.filter(c => {
    if (sevFilter !== 'All' && c.severity !== sevFilter) return false;
    if (behaviorFilter !== 'All' && c.behavior !== behaviorFilter) return false;
    if (serviceFilter !== 'All' && (c.service || 'General') !== serviceFilter) return false;
    if (useCaseFilter !== 'All' && deriveUseCase(c) !== useCaseFilter) return false;
    if (search) {
      const s = search.toLowerCase();
      if (!c.name.toLowerCase().includes(s) && !c.description.toLowerCase().includes(s) && !c.arn.toLowerCase().includes(s)) return false;
    }
    return true;
  });

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await api.post('/api/refresh-catalog');
      localStorage.removeItem('gov_control_catalog');
      localStorage.removeItem('gov_control_catalog_ts');
      setTimeout(() => fetchData(true), 8000);
    }
    catch { /* toast */ }
    finally { setRefreshing(false); }
  };

  return (
    <div>
      <h2>Control Tower Controls</h2>
      <div className="tab-bar">
        <NavLink to="/controls/enabled" className={({ isActive }) => `tab-btn ${isActive ? 'tab-btn--active' : ''}`}>Enabled</NavLink>
        <NavLink to="/controls/catalog" className={({ isActive }) => `tab-btn ${isActive ? 'tab-btn--active' : ''}`}>Catalog ({catalog.length})</NavLink>
      </div>

      {loading ? <div className="muted" style={{ marginTop: 16 }}>Loading catalog…</div> :
       error ? <div className="error-text" style={{ marginTop: 16 }}>{error}</div> : (
        <>
          <div className="catalog-toolbar">
            <input type="text" placeholder="Search controls…" value={search} onChange={e => setSearch(e.target.value)} className="accounts-search" />
            <select value={sevFilter} onChange={e => setSevFilter(e.target.value)} className="accounts-select">
              {severities.map(s => <option key={s} value={s}>{s === 'All' ? 'All Severities' : s}</option>)}
            </select>
            <select value={behaviorFilter} onChange={e => setBehaviorFilter(e.target.value)} className="accounts-select">
              {behaviors.map(b => <option key={b} value={b}>{b === 'All' ? 'All Behaviors' : b}</option>)}
            </select>
            <select value={serviceFilter} onChange={e => setServiceFilter(e.target.value)} className="accounts-select">
              {services.map(s => <option key={s} value={s}>{s === 'All' ? 'All Services' : s}</option>)}
            </select>
            <select value={useCaseFilter} onChange={e => setUseCaseFilter(e.target.value)} className="accounts-select">
              {useCases.map(u => <option key={u} value={u}>{u === 'All' ? 'All Use Cases' : u}</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '0 0 12px' }}>
            <span className="muted">{filtered.length} of {catalog.length} controls</span>
            {isAdmin && (
              <button className="btn btn-secondary" onClick={handleRefresh} disabled={refreshing}>
                {refreshing ? 'Refreshing…' : '↻ Refresh Catalog'}
              </button>
            )}
          </div>
          <div className="catalog-grid">
            {filtered.length === 0 ? <p className="muted">No controls match filters.</p> :
              filtered.map(c => {
                const isEnabled = enabledArns.has(c.arn);
                const useCase = deriveUseCase(c);
                return (
                  <div key={c.arn} className={`catalog-card ${isEnabled ? 'catalog-card--enabled' : ''}`}>
                    <div className="catalog-card-header">
                      <span className="catalog-card-name">{c.name || c.arn.split('/').pop()}</span>
                      <div className="catalog-card-badges">
                        {c.severity && <span className="status-badge" style={{ background: `${SEV_COLORS[c.severity] || '#64748b'}18`, color: SEV_COLORS[c.severity] || '#64748b', border: `1px solid ${SEV_COLORS[c.severity] || '#64748b'}40` }}>{c.severity}</span>}
                        {isEnabled && <span className="status-badge status-badge--enabled">ENABLED</span>}
                      </div>
                    </div>
                    <p className="catalog-card-desc">{c.description || 'No description.'}</p>
                    <div className="catalog-card-tags">
                      {c.behavior && <span className="catalog-tag">{c.behavior}</span>}
                      {c.service && c.service !== 'General' && <span className="catalog-tag catalog-tag--service">{c.service}</span>}
                      {useCase !== 'General' && <span className="catalog-tag catalog-tag--usecase">{useCase}</span>}
                    </div>
                    {isAdmin && !isEnabled && (
                      <button className="btn btn-primary" style={{ marginTop: 10, padding: '5px 12px', fontSize: 11 }} onClick={() => setEnableCtrl({ arn: c.arn, name: c.name })}>Enable</button>
                    )}
                  </div>
                );
              })
            }
          </div>
        </>
      )}

      {enableCtrl && <EnableControlModal controlArn={enableCtrl.arn} controlName={enableCtrl.name} ous={ous} onClose={() => setEnableCtrl(null)} onSuccess={fetchData} />}
    </div>
  );
}
