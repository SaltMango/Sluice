import type { ApiResponse, GlobalStats, DebugStats, TorrentItem, TorrentDetailData } from "../types/api";

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
    fetchApi<TorrentDetailData>(`/torrent/${id}`),

  getStats: () =>
    fetchApi<GlobalStats>("/stats"),

  getDebugStats: (include?: string) =>
    fetchApi<DebugStats>(`/debug${include ? `?include=${encodeURIComponent(include)}` : ""}`),

  pauseTorrent: (id: string) => 
    fetchApi(`/torrent/${id}/pause`, { method: "POST" }),

  resumeTorrent: (id: string) => 
    fetchApi(`/torrent/${id}/resume`, { method: "POST" }),

  removeTorrent: (id: string) => 
    fetchApi(`/torrent/${id}/remove`, { method: "POST" }),

  openFolder: (id: string) => 
    fetchApi(`/torrent/${id}/open-folder`, { method: "POST" }),

  addTorrentFile: async (file: File, save_path?: string) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetchApi<{ torrent_id: string }>(`/torrent/add/file${save_path ? `?save_path=${encodeURIComponent(save_path)}` : ''}`, {
      method: "POST",
      body: formData,
    });
  },

  addTorrentMagnet: (magnet_link: string, save_path?: string) => 
    fetchApi<{ torrent_id: string }>("/torrent/add/magnet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ magnet_link, save_path }),
    }),

  addTorrentUrl: (url: string, save_path?: string) => 
    fetchApi<{ torrent_id: string }>("/torrent/add/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, save_path }),
    }),

  browseFs: (path?: string) =>
    fetchApi<{ current_path: string; parent_path: string | null; directories: { name: string; path: string }[] }>(
        `/fs/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`
    ),

  createDirectory: (path: string, name: string) =>
    fetchApi<{ path: string }>("/fs/mkdir", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, name }),
    }),

  getDownloadsPath: () =>
    fetchApi<{ downloads_path: string }>("/fs/downloads-path"),

  toggleAggressiveMode: (aggressive_mode: boolean) =>
    fetchApi("/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ aggressive_mode }),
    }),
};
