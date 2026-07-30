import { request } from "../request";

export interface PushMessage {
  id: string;
  text: string;
}

export interface PendingApproval {
  request_id: string;
  session_id: string;
  root_session_id: string;
  agent_id: string;
  tool_name: string;
  severity: string;
  findings_count: number;
  findings_summary: string;
  tool_params: Record<string, unknown>;
  created_at: number;
  timeout_seconds: number;
}

// ---------------------------------------------------------------------------
// File event & reading config types
// ---------------------------------------------------------------------------

export interface FileEvent {
  id: string;
  session_id: string;
  file_path: string;
  file_name: string;
  file_size: number;
  tool_name: string;
  action: string;
  created_at: number;
  mime_type: string;
}

export interface FileEventsResponse {
  files: FileEvent[];
  total: number;
}

export interface FileReadingConfigRequest {
  session_id: string;
  file_path: string;
  enabled: boolean;
}

export interface FileReadingConfigResponse {
  disabled_files: string[];
}

export const consoleApi = {
  getPushMessages: (sessionId?: string) =>
    request<{ messages: PushMessage[]; pending_approvals: PendingApproval[] }>(
      sessionId
        ? `/console/push-messages?session_id=${sessionId}`
        : "/console/push-messages",
    ),

  /** Get pending file creation events for a session (consumed on read). */
  getFileEvents: (sessionId: string) =>
    request<FileEventsResponse>(
      `/console/file-events?session_id=${encodeURIComponent(sessionId)}`,
    ),

  /** Remove a file event from the session store. */
  deleteFileEvent: (sessionId: string, filePath: string) =>
    request<{ status: string }>(
      `/console/file-events?session_id=${encodeURIComponent(sessionId)}&file_path=${encodeURIComponent(filePath)}`,
      { method: "DELETE" },
    ),

  /** Delete a file from the server workspace. */
  deleteFile: (filePath: string) =>
    request<{ status: string; filepath: string }>(
      `/files/${encodeURIComponent(filePath)}`,
      { method: "DELETE" },
    ),

  /** Enable or disable reading for a file within a session. */
  updateFileReadingConfig: (body: FileReadingConfigRequest) =>
    request<{ status: string }>("/console/file-reading-config", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Get disabled file paths for a session. */
  getFileReadingConfig: (sessionId: string) =>
    request<FileReadingConfigResponse>(
      `/console/file-reading-config?session_id=${encodeURIComponent(sessionId)}`,
    ),
};
