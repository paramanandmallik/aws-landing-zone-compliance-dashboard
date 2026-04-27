import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';

interface Observation {
  id: string;
  finding: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  affected_resources: string[];
  recommendation: string;
  remediation_action: Record<string, unknown> | null;
  status: 'open' | 'accepted' | 'dismissed';
  created_at: string;
  dismissed_by?: string | null;
  dismissal_justification?: string | null;
}

const SEVERITY_ORDER: Observation['severity'][] = ['critical', 'high', 'medium', 'low'];

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f59e0b',
  medium: '#3b82f6',
  low: '#64748b',
};

const FRAMEWORK_DESCRIPTIONS: Record<string, string> = {
  // NIST CSF v2.0
  'NIST GV.OC-01': 'Govern — Organizational Context: Understand the organization\'s mission and stakeholder expectations',
  'NIST GV.RM-01': 'Govern — Risk Management: Establish and communicate risk management strategy',
  'NIST ID.AM-01': 'Identify — Asset Management: Inventories of hardware, software, and data are maintained',
  'NIST ID.AM-02': 'Identify — Asset Management: Software platforms and applications are inventoried',
  'NIST ID.RA-01': 'Identify — Risk Assessment: Asset vulnerabilities are identified and documented',
  'NIST PR.AA-01': 'Protect — Identity Management: Identities and credentials are issued, managed, and verified',
  'NIST PR.AA-02': 'Protect — Authentication: Users, services, and hardware are authenticated',
  'NIST PR.AA-03': 'Protect — Access Control: Access permissions and authorizations are managed with least privilege',
  'NIST PR.DS-01': 'Protect — Data Security: Data-at-rest is protected with encryption and access controls',
  'NIST PR.DS-02': 'Protect — Data Security: Data-in-transit is protected with encryption',
  'NIST PR.PS-01': 'Protect — Platform Security: Configuration baselines are established and maintained',
  'NIST PR.IR-01': 'Protect — Infrastructure Resilience: Recovery capabilities are maintained',
  'NIST DE.CM-01': 'Detect — Continuous Monitoring: Networks are monitored for anomalous events',
  'NIST DE.CM-02': 'Detect — Continuous Monitoring: Physical environment is monitored for anomalous events',
  'NIST DE.CM-06': 'Detect — Continuous Monitoring: Computing hardware and software are monitored',
  'NIST DE.AE-02': 'Detect — Adverse Event Analysis: Anomalies and indicators of compromise are detected',
  'NIST RS.AN-01': 'Respond — Incident Analysis: Investigations are conducted to understand the incident',
  'NIST RS.MI-01': 'Respond — Incident Mitigation: Incidents are contained and mitigated',
  'NIST RC.RP-01': 'Recover — Recovery Planning: Recovery plan is executed during or after an incident',
  // RBI Master Direction
  'RBI 3.1.a': 'IT Governance — IT Strategy: IT strategy must be aligned with business objectives',
  'RBI 3.1.b': 'IT Governance — Risk Management: IT risk management framework must be established',
  'RBI 3.2': 'IT Governance — Board Oversight: Board must oversee IT governance with audit trails',
  'RBI 4.1': 'IT Infrastructure — Network Security: Secure network architecture with access controls',
  'RBI 4.2': 'IT Infrastructure — Access Control: Strong authentication, MFA, and access management',
  'RBI 4.3': 'IT Infrastructure — Data Security: Encryption at rest and in transit for sensitive data',
  'RBI 4.4': 'IT Infrastructure — Application Security: Secure development and deployment practices',
  'RBI 4.5': 'IT Infrastructure — Endpoint Security: Endpoint protection and patch management',
  'RBI 5.1': 'IT Operations — Change Management: Formal change management process required',
  'RBI 5.2': 'IT Operations — Incident Management: Incident detection, response, and reporting',
  'RBI 5.3': 'IT Operations — Problem Management: Root cause analysis and compliance tracking',
  'RBI 6.1': 'IS Audit — Audit Logging: Comprehensive audit logging in all environments',
  'RBI 6.2': 'IS Audit — Log Retention: Logs must be retained per regulatory requirements',
  'RBI 6.3': 'IS Audit — Audit Trail Integrity: Audit logs must be tamper-proof and validated',
  'RBI 7.1': 'Business Continuity — BCP/DR: Business continuity and disaster recovery plans required',
  'RBI 7.2': 'Business Continuity — Recovery Testing: Regular testing of recovery procedures',
  'RBI 8.1': 'Vendor Management — Third-Party Risk: Vendor risk assessment and service restrictions',
};

function parseFrameworkRefs(finding: string): { refs: string[]; text: string } {
  const match = finding.match(/^\[([^\]]+)\]\s*(.*)/s);
  if (match) {
    const refs = match[1].split('|').map(r => r.trim());
    return { refs, text: match[2] };
  }
  return { refs: [], text: finding };
}

function getRefDescription(ref: string): string {
  // Try exact match first
  if (FRAMEWORK_DESCRIPTIONS[ref]) return FRAMEWORK_DESCRIPTIONS[ref];
  // Try prefix match (e.g., "NIST PR.DS-01" matches "NIST PR.DS-01")
  for (const [key, desc] of Object.entries(FRAMEWORK_DESCRIPTIONS)) {
    if (ref.startsWith(key) || key.startsWith(ref)) return desc;
  }
  return '';
}

function FrameworkBadges({ refs, showDescriptions }: { refs: string[]; showDescriptions?: boolean }) {
  return (
    <div style={{ display: 'flex', flexDirection: showDescriptions ? 'column' : 'row', gap: showDescriptions ? 6 : 4, flexWrap: 'wrap' }}>
      {refs.map((ref, i) => {
        const isRBI = ref.startsWith('RBI');
        const desc = getRefDescription(ref);
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="status-badge" style={{
              background: isRBI ? 'rgba(139,92,246,0.15)' : 'rgba(6,182,212,0.15)',
              color: isRBI ? '#8b5cf6' : '#06b6d4',
              border: `1px solid ${isRBI ? 'rgba(139,92,246,0.3)' : 'rgba(6,182,212,0.3)'}`,
              fontSize: showDescriptions ? 10 : 9, padding: showDescriptions ? '3px 8px' : '2px 6px',
              flexShrink: 0,
            }} title={desc}>{ref}</span>
            {showDescriptions && desc && (
              <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>{desc}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function formatDate(iso: string): string {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span
      className="obs-severity-badge"
      style={{ background: SEVERITY_COLORS[severity] ?? '#999', color: '#fff' }}
    >
      {severity}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    open: '#1565c0',
    accepted: '#2e7d32',
    dismissed: '#757575',
  };
  return (
    <span className="obs-status-badge" style={{ background: colors[status] ?? '#999', color: '#fff' }}>
      {status}
    </span>
  );
}

function ObservationDetail({
  obs,
  isAdmin,
  onAction,
}: {
  obs: Observation;
  isAdmin: boolean;
  onAction: () => void;
}) {
  const [justification, setJustification] = useState('');
  const [showDismiss, setShowDismiss] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const handleAccept = async () => {
    setBusy(true);
    setError('');
    try {
      await api.post(`/api/observations/${obs.id}/accept`);
      onAction();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Accept failed');
    } finally {
      setBusy(false);
    }
  };

  const handleDismiss = async () => {
    if (!justification.trim()) return;
    setBusy(true);
    setError('');
    try {
      await api.post(`/api/observations/${obs.id}/dismiss`, { justification: justification.trim() });
      onAction();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Dismiss failed');
    } finally {
      setBusy(false);
    }
  };

  const { refs, text } = parseFrameworkRefs(obs.finding);

  return (
    <div className="obs-detail">
      {refs.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <h4 style={{ marginBottom: 8, fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px' }}>Framework References</h4>
          <FrameworkBadges refs={refs} showDescriptions />
        </div>
      )}
      <p className="obs-detail-finding">{text}</p>

      {obs.affected_resources.length > 0 && (
        <div className="obs-detail-section">
          <strong>Affected Resources</strong>
          <ul className="obs-resource-list">
            {obs.affected_resources.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}

      <div className="obs-detail-section">
        <strong>Remediation Recommendation</strong>
        <p>{obs.recommendation}</p>
      </div>

      {obs.status === 'open' && isAdmin && (
        <div className="obs-actions">
          <button className="obs-accept-btn" onClick={handleAccept} disabled={busy}>
            {busy ? 'Accepting…' : 'Accept'}
          </button>
          {!showDismiss ? (
            <button className="obs-dismiss-btn" onClick={() => setShowDismiss(true)} disabled={busy}>
              Dismiss
            </button>
          ) : (
            <div className="obs-dismiss-form">
              <textarea
                className="obs-dismiss-textarea"
                placeholder="Justification required…"
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                rows={2}
              />
              <button
                className="obs-dismiss-confirm-btn"
                onClick={handleDismiss}
                disabled={busy || !justification.trim()}
              >
                {busy ? 'Dismissing…' : 'Confirm Dismiss'}
              </button>
              <button className="obs-dismiss-cancel-btn" onClick={() => { setShowDismiss(false); setJustification(''); }}>
                Cancel
              </button>
            </div>
          )}
          {error && <p className="error-text">{error}</p>}
        </div>
      )}

      {obs.status === 'dismissed' && obs.dismissal_justification && (
        <p className="muted">Dismissed: {obs.dismissal_justification}</p>
      )}
    </div>
  );
}

export default function ObservationsPage() {
  const { role } = useAuth();
  const isAdmin = role === 'administrator';
  const [observations, setObservations] = useState<Observation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evalStatus, setEvalStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [evalMsg, setEvalMsg] = useState('');
  const [pollCount, setPollCount] = useState(0);

  const fetchObservations = useCallback(async () => {
    try {
      const res = await api.get<{ data: Observation[] }>('/api/observations');
      setObservations(res.data);
      setError('');
    } catch {
      setError('Failed to load observations');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchObservations(); }, [fetchObservations]);

  // Poll for new observations while evaluation is running
  useEffect(() => {
    if (evalStatus !== 'running') return;
    const interval = setInterval(() => {
      fetchObservations();
      setPollCount(c => {
        if (c >= 24) { // Stop after ~2 minutes
          setEvalStatus('done');
          setEvalMsg('Evaluation complete. Observations updated.');
          return 0;
        }
        return c + 1;
      });
    }, 5000);
    return () => clearInterval(interval);
  }, [evalStatus, fetchObservations]);

  const handleEvaluate = async () => {
    setEvaluating(true);
    setEvalStatus('running');
    setEvalMsg('');
    setPollCount(0);
    try {
      const res = await api.post<{ data: { evaluation_id: string; status: string; message?: string } }>('/api/agent/evaluate');
      setEvalMsg(res.data?.message || 'Evaluation in progress — observations will appear as the agent produces them…');
    } catch (e: unknown) {
      setEvalMsg(e instanceof Error ? e.message : 'Evaluation failed');
      setEvalStatus('error');
    } finally {
      setEvaluating(false);
    }
  };

  const grouped = SEVERITY_ORDER.map((sev) => ({
    severity: sev,
    items: observations.filter((o) => o.severity === sev),
  })).filter((g) => g.items.length > 0);

  return (
    <div>
      <div className="obs-topbar">
        <h2>Observations</h2>
        {isAdmin && (
          <button className="refresh-btn" onClick={handleEvaluate} disabled={evaluating || evalStatus === 'running'}>
            {evaluating ? 'Starting…' : evalStatus === 'running' ? 'Evaluation Running…' : 'Run Evaluation'}
          </button>
        )}
      </div>

      {evalStatus === 'running' && (
        <div className="eval-status-bar">
          <div className="eval-spinner" />
          <span>{evalMsg || 'Agent is evaluating your governance posture against NIST CSF and RBI Master Direction…'}</span>
          <span className="muted">Auto-refreshing every 5s</span>
        </div>
      )}
      {evalStatus === 'done' && <div className="eval-status-bar eval-status-bar--done"><span>{evalMsg}</span></div>}
      {evalStatus === 'error' && <div className="eval-status-bar eval-status-bar--error"><span>{evalMsg}</span></div>}

      {loading && <p className="muted">Loading observations…</p>}
      {error && <p className="error-text">{error}</p>}
      {!loading && !error && observations.length === 0 && (
        <p className="muted">No observations found. Run an evaluation to generate compliance findings.</p>
      )}

      {grouped.map((group) => (
        <div key={group.severity} className="obs-group">
          <h3 className="obs-group-header">
            <SeverityBadge severity={group.severity} />
            <span>{group.severity.charAt(0).toUpperCase() + group.severity.slice(1)}</span>
            <span className="obs-group-count">({group.items.length})</span>
          </h3>
          {group.items.map((obs) => {
            const isExpanded = expandedId === obs.id;
            return (
              <div key={obs.id} className={`obs-row ${isExpanded ? 'obs-row--expanded' : ''}`}>
                <div
                  className="obs-row-summary"
                  onClick={() => setExpandedId(isExpanded ? null : obs.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setExpandedId(isExpanded ? null : obs.id); }}
                >
                  <span className="obs-row-toggle">{isExpanded ? '▾' : '▸'}</span>
                  {(() => { const { refs, text } = parseFrameworkRefs(obs.finding); return (<><FrameworkBadges refs={refs} /><span className="obs-row-finding">{text}</span></>); })()}
                  <StatusBadge status={obs.status} />
                  <span className="obs-row-date">{formatDate(obs.created_at)}</span>
                </div>
                {isExpanded && (
                  <ObservationDetail obs={obs} isAdmin={isAdmin} onAction={fetchObservations} />
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
