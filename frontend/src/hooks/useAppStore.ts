import { create } from "zustand";
import type { NodeOut, EdgeOut, StatsResponse, IndexStatus } from "../types/graph";
import { api } from "../api/client";

interface AppState {
  stats: StatsResponse | null;
  indexStatus: IndexStatus | null;
  watching: boolean;
  nodes: NodeOut[];
  edges: EdgeOut[];
  selectedNode: NodeOut | null;
  searchQuery: string;
  loading: boolean;
  error: string | null;

  fetchStats: () => Promise<void>;
  fetchIndexStatus: () => Promise<void>;
  startIndex: (repoPath: string) => Promise<void>;
  startWatch: (repoPath: string) => Promise<void>;
  stopWatch: () => Promise<void>;
  search: (q: string) => Promise<void>;
  loadAllNodes: () => Promise<void>;
  loadEdges: () => Promise<void>;
  selectNode: (node: NodeOut | null) => void;
  clearError: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  stats: null,
  indexStatus: null,
  watching: false,
  nodes: [],
  edges: [],
  selectedNode: null,
  searchQuery: "",
  loading: false,
  error: null,

  fetchStats: async () => {
    try {
      const stats = await api.stats();
      set({ stats });
    } catch {
      set({ error: "Cannot reach backend" });
    }
  },

  fetchIndexStatus: async () => {
    try {
      const indexStatus = await api.indexStatus();
      set({ indexStatus });
    } catch {}
  },

  startIndex: async (repoPath: string) => {
    set({ loading: true, error: null });
    try {
      await api.startIndex(repoPath);
      const poll = async () => {
        const s = await api.indexStatus();
        set({ indexStatus: s });
        if (s.status === "running") {
          setTimeout(poll, 1000);
        } else {
          set({ loading: false });
          get().fetchStats();
        }
      };
      setTimeout(poll, 800);
    } catch (e: any) {
      set({ loading: false, error: e.message });
    }
  },

  startWatch: async (repoPath: string) => {
    try {
      await api.startWatch(repoPath);
      set({ watching: true });
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  stopWatch: async () => {
    try {
      await api.stopWatch();
      set({ watching: false });
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  search: async (q: string) => {
    set({ searchQuery: q, loading: true });
    try {
      const nodes = q.trim()
        ? await api.searchNodes(q, 100)
        : await api.listNodes(undefined, 200);
      set({ nodes, loading: false });
      if (nodes.length > 0) {
        const edges = await api.listEdges(undefined, 500);
        const nodeIds = new Set(nodes.map((n) => n.id));
        set({ edges: edges.filter((e) => nodeIds.has(e.source_id) && nodeIds.has(e.target_id)) });
      }
    } catch (e: any) {
      set({ loading: false, error: e.message });
    }
  },

  loadAllNodes: async () => {
    set({ loading: true });
    try {
      const nodes = await api.listNodes(undefined, 300);
      set({ nodes, loading: false });
    } catch (e: any) {
      set({ loading: false, error: e.message });
    }
  },

  loadEdges: async () => {
    try {
      const allEdges = await api.listEdges(undefined, 600);
      const nodeIds = new Set(get().nodes.map((n) => n.id));
      set({ edges: allEdges.filter((e) => nodeIds.has(e.source_id) && nodeIds.has(e.target_id)) });
    } catch {}
  },

  selectNode: (node) => set({ selectedNode: node }),
  clearError: () => set({ error: null }),
}));
