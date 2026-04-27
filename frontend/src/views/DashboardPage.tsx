import { useState } from 'react';
import OUTree from '../components/OUTree';
import OUDetail from '../components/OUDetail';
import SummaryCards from '../components/SummaryCards';
import CollectionStatus from '../components/CollectionStatus';
import type { OUNode } from '../components/OUTree';

export default function DashboardPage() {
  const [selectedOU, setSelectedOU] = useState<OUNode | null>(null);

  return (
    <div>
      <h2>Dashboard</h2>
      <CollectionStatus />
      <SummaryCards />
      <div className="org-layout">
        <OUTree selectedOuId={selectedOU?.id ?? null} onSelect={setSelectedOU} />
        <div className="org-detail-area">
          {selectedOU ? (
            <OUDetail ou={selectedOU} />
          ) : (
            <p className="muted">Select an OU from the tree to view details.</p>
          )}
        </div>
      </div>
    </div>
  );
}
