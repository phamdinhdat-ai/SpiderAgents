import { request } from "../request";
import { getApiUrl } from "../config";
import { buildAuthHeaders } from "../authHeaders";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type DocumentStatus = "pending" | "indexing" | "ready" | "error";

export interface KnowledgeDocument {
  id: string;
  filename: string;
  file_path: string;
  kb_name: string;
  mime_type: string;
  size: number;
  status: DocumentStatus;
  chunk_count: number;
  error_message?: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface SearchResult {
  document_id: string;
  filename: string;
  kb_name: string;
  text: string;
  score: number;
  chunk_id: string;
  page_number?: number | null;
  metadata: Record<string, unknown>;
}

export interface KnowledgeBaseInfo {
  name: string;
  document_count: number;
  total_chunks: number;
  created_at: string;
}

export interface IndexingStatus {
  kb_name: string;
  total_documents: number;
  ready_count: number;
  indexing_count: number;
  pending_count: number;
  error_count: number;
  total_chunks: number;
  documents: KnowledgeDocument[];
}

export interface UploadResult {
  document_id: string;
  filename: string;
  kb_name: string;
  status: string;
  chunk_count: number;
  message: string;
}

export interface UploadResponse {
  results: UploadResult[];
  errors: Array<{ filename: string; error: string }>;
  total: number;
}

export interface ListDocumentsResponse {
  documents: KnowledgeDocument[];
  total: number;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  query: string;
}

export interface ListKBResponse {
  knowledge_bases: KnowledgeBaseInfo[];
  total: number;
}

export interface ReindexResponse {
  total: number;
  succeeded: number;
  failed: number;
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

export const knowledgeApi = {
  /** Upload documents to the knowledge base. */
  uploadDocuments: async (
    files: File[],
    kbName: string = "default",
  ): Promise<UploadResponse> => {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));

    const url = getApiUrl(
      `/knowledge/documents/upload?kb_name=${encodeURIComponent(kbName)}`,
    );
    const response = await fetch(url, {
      method: "POST",
      headers: buildAuthHeaders(),
      body: formData,
    });
    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(
        `Upload failed: ${response.status} ${response.statusText}${
          text ? ` - ${text}` : ""
        }`,
      );
    }
    return response.json();
  },

  /** List all documents, optionally filtered by knowledge base. */
  listDocuments: (kbName?: string) => {
    const params = kbName
      ? `?kb_name=${encodeURIComponent(kbName)}`
      : "";
    return request<ListDocumentsResponse>(`/knowledge/documents${params}`);
  },

  /** Get a single document's metadata. */
  getDocument: (documentId: string) =>
    request<KnowledgeDocument>(
      `/knowledge/documents/${encodeURIComponent(documentId)}`,
    ),

  /** Delete a document and its vector chunks. */
  deleteDocument: (documentId: string) =>
    request<{ status: string; document_id: string }>(
      `/knowledge/documents/${encodeURIComponent(documentId)}`,
      { method: "DELETE" },
    ),

  /** Semantic search across the knowledge base. */
  search: (
    query: string,
    kbNames?: string[],
    maxResults: number = 5,
    minScore: number = 0.1,
  ) =>
    request<SearchResponse>("/knowledge/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        kb_names: kbNames ?? null,
        max_results: maxResults,
        min_score: minScore,
      }),
    }),

  /** Get indexing status for a knowledge base. */
  getStatus: (kbName: string = "default") =>
    request<IndexingStatus>(
      `/knowledge/status?kb_name=${encodeURIComponent(kbName)}`,
    ),

  /** Re-index all documents in a knowledge base. */
  reindex: (kbName: string = "default") =>
    request<ReindexResponse>("/knowledge/reindex", {
      method: "POST",
      body: JSON.stringify({ kb_name: kbName }),
    }),

  /** List all knowledge bases with stats. */
  listKnowledgeBases: () =>
    request<ListKBResponse>("/knowledge/list"),
};
