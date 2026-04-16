import React, { useEffect, useState } from "react";
import { formatBytes, formatSpeed, formatTime } from "../../utils/format";
import { engineApi } from "../../services/api";
import type { TorrentDetailData } from "../../types/api";
import { useTorrentStore } from "../../store/useTorrentStore";

interface TorrentDetailProps {
  id: string;
  onBack: () => void;
}

export const TorrentDetail: React.FC<TorrentDetailProps> = ({ id, onBack }) => {
  const [detail, setDetail] = useState<TorrentDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { pauseTorrent, resumeTorrent, removeTorrent } = useTorrentStore();

  useEffect(() => {
    let mounted = true;
    const fetchDetail = async () => {
      try {
        const res = await engineApi.getTorrentDetail(id);
        if (res.success && res.data) {
          if (mounted) setDetail(res.data as TorrentDetailData);
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
            <button className="btn" onClick={() => engineApi.openFolder(detail.id)}>📁 Open Folder</button>
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
        <h3>Learning & Debug Insights</h3>
        
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '24px', marginTop: '16px' }}>
          
          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '16px', borderRadius: '8px' }}>
            <h4 style={{ marginTop: 0, marginBottom: '16px', fontSize: '1rem' }}>Swarm Peer Analysis</h4>
            <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
              <table className="torrent-table" style={{ margin: 0, width: '100%', fontSize: '0.85rem' }}>
                <thead style={{ position: 'sticky', top: 0, zIndex: 1, backgroundColor: 'var(--bg-secondary)' }}>
                  <tr>
                    <th>Endpoint</th>
                    <th>Client</th>
                    <th>Speed</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(!detail.peers_detail || detail.peers_detail.length === 0) ? (
                    <tr><td colSpan={4} style={{ textAlign: 'center', opacity: 0.5 }}>No active peers</td></tr>
                  ) : (
                    detail.peers_detail.map((p, i) => (
                      <tr key={i}>
                        <td style={{ fontFamily: 'monospace' }}>{p.endpoint}</td>
                        <td style={{ maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={p.client}>{p.client || 'Unknown'}</td>
                        <td style={{ color: p.download_speed > 0 ? 'var(--status-downloading)' : 'inherit' }}>
                          {formatSpeed(p.download_speed)}
                        </td>
                        <td>
                          {p.is_choked ? 
                            <span style={{ color: 'var(--status-error)', fontSize: '0.8rem' }}>Choked</span> : 
                            <span style={{ color: 'var(--status-seeding)', fontSize: '0.8rem' }}>Active</span>
                          }
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: '12px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              <i>* Choked peers are throttled by either our engine or theirs to optimize active swarms.</i>
            </div>
          </div>

          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '16px', borderRadius: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h4 style={{ margin: 0, fontSize: '1rem' }}>Piece Distribution Map</h4>
              <div style={{ display: 'flex', gap: '8px', fontSize: '0.75rem' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <div style={{ width: '10px', height: '10px', backgroundColor: 'var(--status-seeding)' }}></div> Complete
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <div style={{ width: '10px', height: '10px', backgroundColor: 'var(--status-downloading)' }}></div> Requested
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <div style={{ width: '10px', height: '10px', backgroundColor: 'var(--bg-primary)' }}></div> Available
                </span>
              </div>
            </div>
            
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(10px, 1fr))', 
              gap: '2px',
              maxHeight: '300px',
              overflowY: 'auto',
              padding: '4px'
            }}>
              {(!detail.pieces || detail.pieces.length === 0) ? (
                <div style={{ gridColumn: '1 / -1', textAlign: 'center', opacity: 0.5, padding: '20px' }}>Loading piece data...</div>
              ) : (
                detail.pieces.map((piece, i) => {
                  let bgColor = 'var(--bg-primary)'; // default available
                  let opacity = 0.3 + (Math.min(piece.availability, 10) / 10) * 0.7; // opacity based on availability
                  
                  if (piece.is_complete) {
                    bgColor = 'var(--status-seeding)';
                    opacity = 1;
                  } else if (piece.state === 'requested' || piece.state === 'downloading') {
                    bgColor = 'var(--status-downloading)';
                    opacity = 1;
                  }
                  
                  return (
                    <div 
                      key={i} 
                      title={`Piece ${piece.index} | State: ${piece.state} | Availability: ${piece.availability}`}
                      style={{
                        aspectRatio: '1/1',
                        backgroundColor: bgColor,
                        opacity: opacity,
                        borderRadius: '1px'
                      }}
                    />
                  );
                })
              )}
            </div>
            {detail.pieces && detail.pieces.length > 0 && (
              <div style={{ marginTop: '12px', fontSize: '0.8rem', color: 'var(--text-secondary)', textAlign: 'right' }}>
                Showing {Math.min(detail.pieces.length, 2000)} pieces
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
