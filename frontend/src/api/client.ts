import axios from "axios";
import type { NodeOut, EdgeOut, StatsResponse, IndexStatus } from "../types/graph";

const http = axios.create({ baseURL: "/api", timeout: 60_000 });

export const api = {
  health:      () => http.get("/status/health").then(r => r.data),
  stats:       () => http.get<StatsResponse>("/status").then(r => r.data),
  indexStatus: () => http.get<IndexStatus>("/index/status").then(r => r.data),
  watchStatus: () => http.get("/index/watch").then(r => r.data),

  startIndex: (repoPath: string) =>
    http.post<IndexStatus>("/index", { repo_path: repoPath }).then(r => r.data),

  startWatch: (repoPath: string) =>
    http.post("/index/watch", { repo_path: repoPath, action: "start" }).then(r => r.data),

  stopWatch: () =>
    http.post("/index/watch", { repo_path: "", action: "stop" }).then(r => r.data),

  searchNodes: (q: string, limit = 30) =>
    http.get<NodeOut[]>("/graph/nodes/search", { params: { q, limit } }).then(r => r.data),

  listNodes: (type?: string, limit = 200) =>
    http.get<NodeOut[]>("/graph/nodes", { params: { type, limit } }).then(r => r.data),

  listEdges: (sourceId?: string, limit = 500) =>
    http.get<EdgeOut[]>("/graph/edges", { params: { source_id: sourceId, limit } }).then(r => r.data),

  fileMap: (path: string) =>
    http.get("/graph/file", { params: { path } }).then(r => r.data),
};
