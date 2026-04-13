import type { ApiResponse, GlobalStats, DebugStats, TorrentItem } from "../types/api";

const API_BASE_URL = "http://localhost:8000/api";

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
    const data: ApiResponse<T> = await response.json();
    return data;
  } catch (error: any) {
    return {
      success: false,
      error: error.message || "Network error",
    };
  }
}

export const engineApi = {
  getTorrents: () => 
    fetchApi<{ torrents: TorrentItem[] }>("/torrents"),

  getTorrentDetail: (id: string) => 
    fetchApi<TorrentItem & { files: any[], trackers: any[] }>(`/torrent/${id}`),

  getStats: () => 
    fetchApi<GlobalStats>("/stats"),

  getDebugStats: () => 
    fetchApi<DebugStats>("/debug"),

  pauseTorrent: (id: string) => 
    fetchApi(`/torrent/${id}/pause`, { method: "POST" }),

  resumeTorrent: (id: string) => 
    fetchApi(`/torrent/${id}/resume`, { method: "POST" }),

  removeTorrent: (id: string) => 
    fetchApi(`/torrent/${id}/remove`, { method: "POST" }),

  addTorrentFile: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetchApi<{ torrent_id: string }>("/torrent/add/file", {
      method: "POST",
      body: formData,
    });
  },

  addTorrentMagnet: (magnet_link: string) => 
    fetchApi<{ torrent_id: string }>("/torrent/add/magnet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ magnet_link }),
    }),

  addTorrentUrl: (url: string) => 
    fetchApi<{ torrent_id: string }>("/torrent/add/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }),

  toggleAggressiveMode: (aggressive_mode: boolean) =>
    fetchApi("/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ aggressive_mode }),
    }),
};
