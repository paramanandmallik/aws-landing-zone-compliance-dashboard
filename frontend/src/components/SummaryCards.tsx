import { useState, useEffect } from 'react';
import { api } from '../services/api';

interface Counts {
  accounts: number;
  ous: number;
  scps: number;
  controls: number;
}

export default function SummaryCards() {
  const [counts, setCounts] = useState<Counts>({ accounts: 0, ous: 0, scps: 0, controls: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<{ data: unknown[] }>('/api/accounts').then(r => r.data.length).catch(() => 0),
      api.get<{ data: unknown[] }>('/api/ous').then(r => countOUs(r.data)).catch(() => 0),
      api.get<{ data: unknown[] }>('/api/scps').then(r => r.data.length).catch(() => 0),
      api.get<{ data: unknown[] }>('/api/controls').then(r => r.data.length).catch(() => 0),
    ]).then(([accounts, ous, scps, controls]) => {
      setCounts({ accounts, ous, scps, controls });
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="summary-cards"><p>Loading summary…</p></div>;

  const cards = [
    { label: 'Total Accounts', value: counts.accounts },
    { label: 'Total OUs', value: counts.ous },
    { label: 'Total SCPs', value: counts.scps },
    { label: 'Enabled Controls', value: counts.controls },
  ];

  return (
    <div className="summary-cards">
      {cards.map(c => (
        <div key={c.label} className="summary-card">
          <span className="summary-card-value">{c.value}</span>
          <span className="summary-card-label">{c.label}</span>
        </div>
      ))}
    </div>
  );
}

/** Recursively count all OUs in a tree structure */
function countOUs(nodes: any[]): number {
  let count = 0;
  for (const node of nodes) {
    count += 1;
    if (node.children?.length) count += countOUs(node.children);
  }
  return count;
}
