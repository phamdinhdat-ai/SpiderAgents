import { getApiUrl } from "../config";

function getToken(): string {
  return localStorage.getItem("qwenpaw_auth_token") || "";
}

function authHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${getToken()}` };
}

export interface AdminStatusResponse {
  username: string;
  role: string;
}

/** Per-user activity summary as returned by GET /auth/admin/sessions */
export interface UserActivitySummary {
  username: string;
  role: string;
  total_sessions: number;
  active_sessions: number;
  total_messages: number;
  last_active: string;
  created_at: string;
}

/** Response for GET /auth/admin/sessions */
export interface AdminSessionsResponse {
  users: UserActivitySummary[];
  total_users: number;
  total_sessions: number;
  active_sessions: number;
}

/** Single session for a user */
export interface UserSessionInfo {
  session_id: string;
  channel: string;
  last_active: string;
  message_count: number;
  status: string;
}

/** Response for GET /auth/admin/users/{username}/sessions */
export interface AdminUserSessionsResponse {
  username: string;
  sessions: UserSessionInfo[];
  total: number;
}

export interface UserInfo {
  username: string;
  role: string;
}

export interface UserListResponse {
  users: UserInfo[];
  total: number;
}

export const adminApi = {
  getAdminStatus: async (): Promise<AdminStatusResponse> => {
    const res = await fetch(getApiUrl("/auth/admin/status"), {
      headers: authHeaders(),
    });
    if (!res.ok) {
      if (res.status === 403) throw new Error("Admin access required");
      throw new Error("Failed to check admin status");
    }
    return res.json();
  },

  /** Get all-user session summary (admin dashboard) */
  getSessions: async (agentId = "default"): Promise<AdminSessionsResponse> => {
    const res = await fetch(
      getApiUrl(`/auth/admin/sessions?agent_id=${encodeURIComponent(agentId)}`),
      { headers: authHeaders() },
    );
    if (!res.ok) throw new Error("Failed to fetch sessions");
    return res.json();
  },

  /** Get a specific user's sessions */
  getUserSessions: async (
    username: string,
    agentId = "default",
  ): Promise<AdminUserSessionsResponse> => {
    const res = await fetch(
      getApiUrl(
        `/auth/admin/users/${encodeURIComponent(username)}/sessions?agent_id=${encodeURIComponent(agentId)}`,
      ),
      { headers: authHeaders() },
    );
    if (!res.ok) throw new Error("Failed to fetch user sessions");
    return res.json();
  },

  /** Admin-delete a specific user session */
  deleteUserSession: async (
    username: string,
    sessionId: string,
    agentId = "default",
  ): Promise<{ message: string }> => {
    const res = await fetch(
      getApiUrl(
        `/auth/admin/users/${encodeURIComponent(username)}/sessions/${encodeURIComponent(sessionId)}?agent_id=${encodeURIComponent(agentId)}`,
      ),
      { method: "DELETE", headers: authHeaders() },
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to delete user session");
    }
    return res.json();
  },

  /** Force-logout a user (revoke all tokens) */
  revokeUserTokens: async (
    username: string,
  ): Promise<{ message: string; revoked: boolean }> => {
    const res = await fetch(
      getApiUrl(
        `/auth/admin/users/${encodeURIComponent(username)}/revoke-tokens`,
      ),
      { method: "POST", headers: authHeaders() },
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to revoke tokens");
    }
    return res.json();
  },

  listUsers: async (): Promise<UserListResponse> => {
    const res = await fetch(getApiUrl("/auth/admin/users"), {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch users");
    return res.json();
  },

  createUser: async (
    username: string,
    password: string,
    role: string,
  ): Promise<{ message: string; username: string; role: string }> => {
    const res = await fetch(getApiUrl("/auth/admin/create-user"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify({ username, password, role }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to create user");
    }
    return res.json();
  },

  updateRole: async (
    username: string,
    role: string,
  ): Promise<{ message: string; username: string; role: string }> => {
    const res = await fetch(
      getApiUrl(`/auth/admin/users/${encodeURIComponent(username)}/role`),
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ role }),
      },
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to update role");
    }
    return res.json();
  },

  deleteUser: async (
    username: string,
  ): Promise<{ message: string }> => {
    const res = await fetch(
      getApiUrl(`/auth/admin/users/${encodeURIComponent(username)}`),
      {
        method: "DELETE",
        headers: authHeaders(),
      },
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to delete user");
    }
    return res.json();
  },
};
