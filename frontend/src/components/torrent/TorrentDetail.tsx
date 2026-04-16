import React, { useEffect, useState } from "react";
import { formatBytes, formatSpeed, formatTime } from "../../utils/format";
import { engineApi } from "../../services/api";
import type { TorrentItem } from "../../types/api";
import { useTorrentStore } from "../../store/useTorrentStore";
import { DebugPanel } from "../debug/DebugPanel";

interface TorrentDetailProps {
  id: string;
  onBack: () => void;
}

export const TorrentDetail: React.FC<TorrentDetailProps> = ({ id, onBack }) => {
  const [detail, setDetail] = useState<TorrentItem & { files: {name: string, size: number, progress: number}[], trackers: unknown[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { pauseTorrent, resumeTorrent, removeTorrent } = useTorrentStore();

  useEffect(() => {
    let mounted = true;
    const fetchDetail = async () => {
      try {
        const res = await engineApi.getTorrentDetail(id);
        if (res.success && res.data) {
          if (mounted) setDetail(res.data);
        } else {
          if (mounted) setError(res.error || "Failed to fetch detail");
        }
      } catch (err: unknown) {
        if (mounted) setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchDetail();
    const interval = setInterval(fetchDetail, 2000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [id]);

  if (loading && !detail) {
    return <div style={{ padding: '24px' }}>Loading...</div>;
  }

  if (error || !detail) {
    return (
      <div style={{ padding: '24px' }}>
        <button className="btn" onClick={onBack} style={{ marginBottom: '16px' }}>← Back</button>
        <div style={{ color: 'var(--status-error)' }}>{error || "Torrent not found"}</div>
      </div>
    );
  }

  const percent = (detail.progress * 100).toFixed(1);

  return (
    <div className="torrent-detail" style={{ padding: '20px', maxWidth: '100%', overflowX: 'hidden' }}>
      <button className="btn" onClick={onBack} style={{ marginBottom: '24px' }}>← Back to List</button>
      
      <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '20px', borderRadius: '8px', marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '1.5rem', wordBreak: 'break-all' }}>{detail.name}</h2>
            <div style={{ display: 'flex', gap: '16px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              <span>{formatBytes(detail.downloaded)} / {formatBytes(detail.size)}</span>
              <span className={`status-badge status-${detail.status}`}>{detail.status}</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            {detail.status === "downloading" || detail.status === "checking" ? (
              <button className="btn" onClick={() => pauseTorrent(detail.id)}>⏸ Pause</button>
            ) : (
              <button className="btn" onClick={() => resumeTorrent(detail.id)}>▶ Resume</button>
            )}
            <button className="btn btn-danger" onClick={() => { removeTorrent(detail.id); onBack(); }}>✕ Remove</button>
          </div>
        </div>

        <div className="progress-container" style={{ height: '12px', marginBottom: '8px' }}>
          <div 
            className="progress-fill" 
            style={{ 
              width: `${Math.min(Number(percent), 100)}%`,
              backgroundColor: `var(--status-${detail.status})` 
            }} 
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
          <span>{percent}% Complete</span>
          <span>ETA: {detail.status === 'downloading' ? formatTime(detail.eta) : "-"}</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginTop: '24px' }}>
          <div className="stat-card" style={{ padding: '12px', backgroundColor: 'var(--bg-primary)', borderRadius: '6px' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Download Speed</div>
            <div style={{ fontSize: '1.2rem', fontWeight: 600 }}>{formatSpeed(detail.download_speed)}</div>
          </div>
          <div className="stat-card" style={{ padding: '12px', backgroundColor: 'var(--bg-primary)', borderRadius: '6px' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Upload Speed</div>
            <div style={{ fontSize: '1.2rem', fontWeight: 600 }}>{formatSpeed(detail.upload_speed)}</div>
          </div>
          <div className="stat-card" style={{ padding: '12px', backgroundColor: 'var(--bg-primary)', borderRadius: '6px' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Peers / Seeds</div>
            <div style={{ fontSize: '1.2rem', fontWeight: 600 }}>{detail.peers} / {detail.seeds}</div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '24px' }}>
        <div>
          <h3>Files</h3>
          <div style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '8px', overflow: 'hidden' }}>
            <table className="torrent-table" style={{ margin: 0, width: '100%' }}>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Size</th>
                  <th>Progress</th>
                </tr>
              </thead>
              <tbody>
                {detail.files.map((f, i) => (
                  <tr key={i}>
                    <td>{f.name}</td>
                    <td>{formatBytes(f.size)}</td>
                    <td>{(f.progress * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      
      <div style={{ marginTop: '24px' }}>
        <h3>Engine Debug Info</h3>
        <div style={{ position: 'relative', width: '100%', maxWidth: '400px' }}>
          <DebugPanel />
        </div>
      </div>
    </div>
  );
};
