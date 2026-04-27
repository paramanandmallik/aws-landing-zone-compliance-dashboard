import { useState, useEffect } from 'react';
import { api } from '../services/api';

export interface OUNode {
  id: string;
  name: string;
  arn: string;
  parent_ou_id: string | null;
  path: string;
  children: OUNode[];
}

interface OUTreeProps {
  selectedOuId: string | null;
  onSelect: (ou: OUNode) => void;
}

function TreeNode({ node, depth, selectedOuId, onSelect }: {
  node: OUNode;
  depth: number;
  selectedOuId: string | null;
  onSelect: (ou: OUNode) => void;
}) {
  const [expanded, setExpanded] = useState(depth === 0);
  const hasChildren = node.children.length > 0;
  const isSelected = node.id === selectedOuId;

  return (
    <div>
      <div
        className={`ou-tree-node${isSelected ? ' ou-tree-node--selected' : ''}`}
        style={{ paddingLeft: depth * 20 + 8 }}
        onClick={() => onSelect(node)}
      >
        {hasChildren && (
          <span
            className="ou-tree-toggle"
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
          >
            {expanded ? '▾' : '▸'}
          </span>
        )}
        {!hasChildren && <span className="ou-tree-toggle" style={{ visibility: 'hidden' }}>▸</span>}
        <span className="ou-tree-label">{node.name}</span>
      </div>
      {expanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedOuId={selectedOuId}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function OUTree({ selectedOuId, onSelect }: OUTreeProps) {
  const [roots, setRoots] = useState<OUNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get<{ data: OUNode[] }>('/api/ous')
      .then((res) => setRoots(res.data))
      .catch((err) => setError(err.message || 'Failed to load OUs'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="ou-tree-panel"><p>Loading…</p></div>;
  if (error) return <div className="ou-tree-panel"><p className="error-text">{error}</p></div>;
  if (roots.length === 0) return <div className="ou-tree-panel"><p>No organizational units found.</p></div>;

  return (
    <div className="ou-tree-panel">
      <h3 style={{ margin: '0 0 8px' }}>Organization</h3>
      {roots.map((root) => (
        <TreeNode key={root.id} node={root} depth={0} selectedOuId={selectedOuId} onSelect={onSelect} />
      ))}
    </div>
  );
}
