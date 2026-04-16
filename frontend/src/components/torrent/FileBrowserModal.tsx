import React, { useEffect, useState } from "react";
import { engineApi } from "../../services/api";

interface FileBrowserModalProps {
  onClose: () => void;
  onSelect: (path: string) => void;
  initialPath?: string;
}

export const FileBrowserModal: React.FC<FileBrowserModalProps> = ({ onClose, onSelect, initialPath }) => {
  const [currentPath, setCurrentPath] = useState<string>(initialPath || "");
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [directories, setDirectories] = useState<{name: string, path: string}[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDirectory = async (path?: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await engineApi.browseFs(path);
      if (res.success && res.data) {
        setCurrentPath(res.data.current_path);
        setParentPath(res.data.parent_path);
        setDirectories(res.data.directories);
      } else {
        setError(res.error || "Failed to load directories");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error occurred");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDirectory(currentPath || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="modal-overlay" onClick={onClose} style={{ zIndex: 1000 }}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ width: '500px', maxWidth: '90%' }}>
        <div className="modal-header">
          <h2>Select Save Location</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label className="form-label">Current Path</label>
          <input 
            type="text" 
            className="form-input" 
            value={currentPath}
            onChange={(e) => setCurrentPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                fetchDirectory(currentPath);
              }
            }}
          />
        </div>

        {error && <div style={{ color: 'var(--status-error)', fontSize: '0.875rem', marginBottom: '16px' }}>{error}</div>}

        <div style={{
          border: '1px solid var(--border-color)',
          borderRadius: '4px',
          height: '300px',
          overflowY: 'auto',
          backgroundColor: 'var(--bg-secondary)',
          marginBottom: '16px'
        }}>
          {loading ? (
            <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-secondary)' }}>Loading...</div>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {parentPath && (
                <li 
                  onClick={() => fetchDirectory(parentPath)}
                  style={{ 
                    padding: '8px 16px', 
                    cursor: 'pointer', 
                    borderBottom: '1px solid var(--border-color)' 
                  }}
                  onMouseOver={(e) => e.currentTarget.style.backgroundColor = 'var(--bg-hover)'}
                  onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                >
                  📁 ..
                </li>
              )}
              {directories.length === 0 && !loading && (
                <li style={{ padding: '16px', textAlign: 'center', color: 'var(--text-secondary)' }}>No directories found</li>
              )}
              {directories.map((dir) => (
                <li 
                  key={dir.path}
                  onClick={() => fetchDirectory(dir.path)}
                  style={{ 
                    padding: '8px 16px', 
                    cursor: 'pointer', 
                    borderBottom: '1px solid var(--border-color)' 
                  }}
                  onMouseOver={(e) => e.currentTarget.style.backgroundColor = 'var(--bg-hover)'}
                  onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                >
                  📁 {dir.name}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={() => onSelect(currentPath)}>
            Select Folder
          </button>
        </div>
      </div>
    </div>
  );
};
