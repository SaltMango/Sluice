import React, { useState, useEffect } from "react";
import { engineApi } from "../../services/api";
import { useTorrentStore } from "../../store/useTorrentStore";
import { FileBrowserModal } from "./FileBrowserModal";

interface AddTorrentModalProps {
  onClose: () => void;
}

export const AddTorrentModal: React.FC<AddTorrentModalProps> = ({ onClose }) => {
  const [tab, setTab] = useState<"magnet" | "url" | "file">("magnet");
  const [inputValue, setInputValue] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savePath, setSavePath] = useState("");
  const [showFileBrowser, setShowFileBrowser] = useState(false);
  const fetchData = useTorrentStore((state) => state.fetchData);

  useEffect(() => {
    engineApi.getDownloadsPath().then((res) => {
      if (res.success && res.data) {
        setSavePath(res.data.downloads_path);
      }
    }).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      let res;
      if (tab === "magnet") {
        if (!inputValue) throw new Error("Magnet link is required");
        res = await engineApi.addTorrentMagnet(inputValue, savePath || undefined);
      } else if (tab === "url") {
        if (!inputValue) throw new Error("URL is required");
        res = await engineApi.addTorrentUrl(inputValue, savePath || undefined);
      } else {
        if (!file) throw new Error("File is required");
        res = await engineApi.addTorrentFile(file, savePath || undefined);
      }

      if (res.success) {
        await fetchData(); // Refresh list immediately
        onClose();
      } else {
        setError(res.error || "Failed to add torrent");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Add New Torrent</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="tabs">
          <div className={`tab ${tab === "magnet" ? "active" : ""}`} onClick={() => setTab("magnet")}>Magnet Link</div>
          <div className={`tab ${tab === "url" ? "active" : ""}`} onClick={() => setTab("url")}>URL</div>
          <div className={`tab ${tab === "file" ? "active" : ""}`} onClick={() => setTab("file")}>Torrent File</div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            {tab === "file" ? (
              <>
                <label className="form-label">Select .torrent File</label>
                <input 
                  type="file" 
                  accept=".torrent"
                  className="form-input" 
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </>
            ) : (
              <>
                <label className="form-label">{tab === "magnet" ? "Magnet Link" : "Direct URL"}</label>
                <input 
                  type="text" 
                  className="form-input" 
                  autoFocus
                  placeholder={tab === "magnet" ? "magnet:?xt=urn:btih:..." : "https://example.com/file.torrent"}
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                />
              </>
            )}
          </div>

          <div className="form-group" style={{ marginTop: '16px' }}>
            <label className="form-label">Save Location (Optional)</label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input 
                type="text" 
                className="form-input" 
                placeholder="Default Downloads Folder"
                value={savePath}
                onChange={(e) => setSavePath(e.target.value)}
                style={{ flex: 1 }}
              />
              <button 
                type="button" 
                className="btn" 
                onClick={() => setShowFileBrowser(true)}
              >
                Browse...
              </button>
            </div>
          </div>

          {error && <div style={{color: 'var(--status-error)', fontSize: '0.875rem', marginBottom: '16px'}}>{error}</div>}

          <div className="modal-actions">
            <button type="button" className="btn" onClick={onClose} disabled={loading}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? "Adding..." : "Add Torrent"}
            </button>
          </div>
        </form>
      </div>

      {showFileBrowser && (
        <FileBrowserModal 
          onClose={() => setShowFileBrowser(false)} 
          onSelect={(path) => {
            setSavePath(path);
            setShowFileBrowser(false);
          }} 
          initialPath={savePath}
        />
      )}
    </div>
  );
};
