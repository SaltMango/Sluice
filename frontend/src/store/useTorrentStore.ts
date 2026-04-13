import { create } from "zustand";
import type { GlobalStats, TorrentItem } from "../types/api";
import { engineApi } from "../services/api";

interface TorrentStore {
  torrents: TorrentItem[];
  stats: GlobalStats;
  isLoading: boolean;
  error: string | null;
  
  // Actions
  fetchData: () => Promise<void>;
  pauseTorrent: (id: string) => Promise<void>;
  resumeTorrent: (id: string) => Promise<void>;
  removeTorrent: (id: string) => Promise<void>;
  toggleAggressiveMode: (mode: boolean) => Promise<void>;
}

export const useTorrentStore = create<TorrentStore>((set, get) => ({
  torrents: [],
  stats: {
    global_speed_down: 0,
    global_speed_up: 0,
    total_peers: 0,
    active_torrents: 0,
    aggressive_mode: false,
  },
  isLoading: true,
  error: null,

  fetchData: async () => {
    try {
      const [torrentsRes, statsRes] = await Promise.all([
        engineApi.getTorrents(),
        engineApi.getStats()
      ]);

      if (torrentsRes.success && statsRes.success) {
        set({
          torrents: torrentsRes.data?.torrents || [],
          stats: statsRes.data || get().stats,
          isLoading: false,
          error: null
        });
      } else {
        set({ 
          error: torrentsRes.error || statsRes.error || "Failed to fetch data",
          isLoading: false 
        });
      }
    } catch (err: any) {
      set({ error: err.message, isLoading: false });
    }
  },

  pauseTorrent: async (id: string) => {
    // Optimistic update
    set((state) => ({
      torrents: state.torrents.map(t => 
        t.id === id ? { ...t, status: "paused" } : t
      )
    }));
    await engineApi.pauseTorrent(id);
    await get().fetchData();
  },

  resumeTorrent: async (id: string) => {
    // Optimistic update
    set((state) => ({
      torrents: state.torrents.map(t => 
        t.id === id ? { ...t, status: "downloading" } : t
      )
    }));
    await engineApi.resumeTorrent(id);
    await get().fetchData();
  },

  removeTorrent: async (id: string) => {
    // Optimistic update
    set((state) => ({
      torrents: state.torrents.filter(t => t.id !== id)
    }));
    await engineApi.removeTorrent(id);
    await get().fetchData();
  },

  toggleAggressiveMode: async (mode: boolean) => {
    // Optimistic update
    set((state) => ({
      stats: { ...state.stats, aggressive_mode: mode }
    }));
    await engineApi.toggleAggressiveMode(mode);
    await get().fetchData();
  }
}));
