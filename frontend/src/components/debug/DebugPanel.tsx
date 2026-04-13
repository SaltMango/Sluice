import { useState, useEffect } from 'react';
import { useTorrentStore } from '../../store/useTorrentStore';
import { formatSpeed } from '../../utils/format';
import './DebugPanel.css';

export function DebugPanel() {
  const storeDebugStats = useTorrentStore(state => state.debugStats);
  
  const [isPaused, setIsPaused] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [displayStats, setDisplayStats] = useState(storeDebugStats);

  useEffect(() => {
    if (!isPaused && storeDebugStats) {
      setDisplayStats(storeDebugStats);
    }
  }, [storeDebugStats, isPaused]);

  if (!displayStats) return null;

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
            {displayStats.scheduler_mode}
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
          <span className="debug-value">{displayStats.active_pieces}</span>
        </div>
        
        <div className="debug-row">
          <span>Avg Peer Speed</span>
          <span className="debug-value">{formatSpeed(displayStats.average_peer_speed)}</span>
        </div>
        
        <div className="debug-row">
          <span>Fast vs Slow Peers</span>
          <span className="debug-value">
            <span style={{color: 'var(--status-completed)'}}>{displayStats.fast_peers}</span> 
            {' / '} 
            <span style={{color: 'var(--status-paused)'}}>{displayStats.slow_peers}</span>
          </span>
        </div>
        
        <div className="debug-row" style={{ flexDirection: 'column', marginTop: '12px', marginBottom: '0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span>BW Utilization</span>
            <span className="debug-value">{displayStats.bandwidth_utilization_percent.toFixed(1)}%</span>
          </div>
          <div className="debug-progress-bar">
            <div 
              className="debug-progress-fill" 
              style={{ width: `${Math.min(100, Math.max(0, displayStats.bandwidth_utilization_percent))}%` }} 
            />
          </div>
        </div>
      </div>
    </div>
  );
}
