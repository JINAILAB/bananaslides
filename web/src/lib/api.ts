import type { ChangedItem, EditorBox, EditorState, JobMode, JobRecord } from "./types";

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
export const API_BASE_URL = rawBaseUrl.replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : null;
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : response.statusText;
    throw new Error(detail || "Request failed.");
  }
  return payload as T;
}

export function apiFileUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

export async function createJob(mode: JobMode, files: File[]): Promise<{ job_id: string; status: string }> {
  const formData = new FormData();
  formData.append("mode", mode);
  for (const file of files) {
    formData.append("files", file);
  }
  return request("/jobs", {
    method: "POST",
    body: formData,
  });
}

export async function prepareJob(jobId: string): Promise<JobRecord> {
  return request(`/jobs/${jobId}/prepare`, { method: "POST" });
}

export async function processJob(jobId: string): Promise<{ ok: boolean; job_id: string }> {
  return request(`/jobs/${jobId}/process`, { method: "POST" });
}

export async function fetchJob(jobId: string): Promise<JobRecord> {
  return request(`/jobs/${jobId}`);
}

export async function fetchEditorState(jobId: string, slideNumber: number): Promise<EditorState> {
  const payload = await request<EditorState>(`/jobs/${jobId}/slides/${slideNumber}/editor-state`);
  return {
    ...payload,
    image_url: apiFileUrl(payload.image_url),
  };
}

export async function saveEditorState(
  jobId: string,
  slideNumber: number,
  boxes: EditorBox[],
): Promise<{ ok: boolean; changed_items: ChangedItem[] }> {
  return request(`/jobs/${jobId}/slides/${slideNumber}/editor-save`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ boxes }),
  });
}

export async function applySlide(
  jobId: string,
  slideNumber: number,
): Promise<{ ok: boolean; changed_items: ChangedItem[] }> {
  return request(`/jobs/${jobId}/slides/${slideNumber}/apply`, {
    method: "POST",
  });
}

export async function buildDeck(jobId: string): Promise<{ ok: boolean; deck_pptx: string }> {
  return request(`/jobs/${jobId}/build-deck`, {
    method: "POST",
  });
}
