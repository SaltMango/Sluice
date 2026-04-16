import { useState, useEffect, useMemo } from 'react';
import { useTorrentStore } from '../../store/useTorrentStore';
import { formatSpeed } from '../../utils/format';
import type { DebugStats } from '../../types/api';
import './DebugPanel.css';

export function DebugPanel() {
  const storeDebugStats = useTorrentStore(state => state.debugStats) as DebugStats | null;

  const [isPaused, setIsPaused] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [displayStats, setDisplayStats] = useState<DebugStats | null>(storeDebugStats);

  useEffect(() => {
    if (!isPaused && storeDebugStats) {
      setDisplayStats(storeDebugStats);
    }
  }, [storeDebugStats, isPaused]);

  // Derive flat fields from the new nested structure for backward-compat display
  const flat = useMemo(() => {
    if (!displayStats) return null;
    const g = displayStats.global;
    const speed = g.speed;
    const health = g.health;
    const sched = displayStats.scheduler;

    // Aggregate fast/normal/idle across all torrents
    let totalFast = 0, totalNormal = 0, totalIdle = 0, totalActive = 0;
    for (const t of displayStats.torrents ?? []) {
      const fast   = t.metrics?.peers?.fast    ?? 0;
      const active = t.metrics?.peers?.active  ?? 0;
      const slow   = t.metrics?.peers?.slow    ?? 0;
      totalFast   += fast;
      totalNormal += Math.max(0, active - fast);
      totalIdle   += slow;
      totalActive += t.metrics?.pieces?.active ?? 0;
    }

    return {
      scheduler_mode: sched?.mode ?? 'balanced',
      active_pieces: totalActive,
      average_peer_speed: speed?.avg_10s ?? g.total_speed_down / Math.max(g.total_peers, 1),
      fast_peers: totalFast,
      normal_peers: totalNormal,
      idle_peers: totalIdle,
      bandwidth_utilization_percent: (health?.bandwidth_utilization ?? 0) * 100,
    };
  }, [displayStats]);

  if (!displayStats || !flat) return null;

  if (isMinimized) {
    return (
      <div className="debug-panel-minimized" onClick={() => setIsMinimized(false)}>
        Engine Debug 🔍
      </div>
    );
  }

  return (
    <div className="debug-panel">
      <div className="debug-header-controls">
        <h3>
          Engine Debug
          <span style={{ fontSize: '0.7rem', background: 'var(--primary)', color: 'black', padding: '2px 6px', borderRadius: '4px', marginLeft: '8px' }}>
            {flat.scheduler_mode}
          </span>
        </h3>
        <div className="debug-actions">
           <button
             onClick={() => setIsPaused(!isPaused)}
             className={`debug-btn ${isPaused ? 'paused' : ''}`}
             title={isPaused ? "Resume Updates" : "Pause Updates"}
           >
             {isPaused ? "▶" : "⏸"}
           </button>
           <button onClick={() => setIsMinimized(true)} className="debug-btn" title="Minimize Panel">
             ✖
           </button>
        </div>
      </div>

      <div className={`debug-content ${isPaused ? 'paused' : ''}`}>
        <div className="debug-row">
          <span>Active Pieces</span>
          <span className="debug-value">{flat.active_pieces}</span>
        </div>

        <div className="debug-row">
          <span>Avg Peer Speed</span>
          <span className="debug-value">{formatSpeed(flat.average_peer_speed)}</span>
        </div>

        <div className="debug-row">
          <span>Peers</span>
          <span className="debug-value">
            <span style={{color: 'var(--status-completed)'}} title="Fast: top-25% speed">{flat.fast_peers}F</span>
            {' · '}
            <span style={{color: 'var(--status-downloading)'}} title="Normal: active, not top-25%">{flat.normal_peers}N</span>
            {' · '}
            <span style={{color: 'var(--text-tertiary)'}} title="Idle: zero transfer speed">{flat.idle_peers}I</span>
          </span>
        </div>

        <div className="debug-row" style={{ flexDirection: 'column', marginTop: '12px', marginBottom: '0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span>BW Utilization</span>
            <span className="debug-value">{flat.bandwidth_utilization_percent.toFixed(1)}%</span>
          </div>
          <div className="debug-progress-bar">
            <div
              className="debug-progress-fill"
              style={{ width: `${Math.min(100, Math.max(0, flat.bandwidth_utilization_percent))}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
