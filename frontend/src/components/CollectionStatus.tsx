import { useState, useEffect } from 'react';
import { api } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

interface CollectionInfo {
  timestamp: string;
  status: string;
}

export default function CollectionStatus() {
  const { role } = useAuth();
  const [info, setInfo] = useState<CollectionInfo | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const fetchStatus = () => {
    api.get<{ data: CollectionInfo }>('/api/collection-status')
      .then(r => setInfo(r.data))
      .catch(() => setError('Unable to load collection status'));
  };

  useEffect(fetchStatus, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await api.post('/api/collect');
      // Re-fetch status after triggering collection
      setTimeout(fetchStatus, 2000);
    } catch {
      setError('Failed to trigger refresh');
    } finally {
      setRefreshing(false);
    }
  };

  const formatTimestamp = (ts: string) => {
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  return (
    <div className="collection-status">
      {error && <span className="error-text">{error}</span>}
      {info && (
        <>
          <span className="collection-ts">
            Last collected: <strong>{formatTimestamp(info.timestamp)}</strong>
          </span>
          <span className={`collection-badge collection-badge--${info.status}`}>
            {info.status}
          </span>
        </>
      )}
      {role === 'administrator' && (
        <button
          className="refresh-btn"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          {refreshing ? 'Refreshing…' : 'Refresh Now'}
        </button>
      )}
    </div>
  );
}
