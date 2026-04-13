import { useEffect, useState } from "react";
import { TopBar } from "./components/layout/TopBar";
import { StatsBar } from "./components/layout/StatsBar";
import { TorrentTable } from "./components/torrent/TorrentTable";
import { AddTorrentModal } from "./components/torrent/AddTorrentModal";
import { useTorrentStore } from "./store/useTorrentStore";

function App() {
  const [showAddModal, setShowAddModal] = useState(false);
  const fetchData = useTorrentStore((state) => state.fetchData);
  const error = useTorrentStore((state) => state.error);

  useEffect(() => {
    // Initial fetch
    fetchData();

    // Polling interval
    const interval = setInterval(() => {
      fetchData();
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(interval);
  }, [fetchData]);

  return (
    <div className="app-container">
      <TopBar onAddClick={() => setShowAddModal(true)} />
      
      <main className="main-content">
        {error && (
          <div style={{
            background: 'rgba(239, 71, 111, 0.1)', 
            color: 'var(--status-error)', 
            padding: '12px 16px', 
            borderRadius: '6px', 
            marginBottom: '20px',
            border: '1px solid rgba(239, 71, 111, 0.2)'
          }}>
            Connection Error: {error}
          </div>
        )}
        
        <TorrentTable />
      </main>

      <StatsBar />

      {showAddModal && <AddTorrentModal onClose={() => setShowAddModal(false)} />}
    </div>
  );
}

export default App;
