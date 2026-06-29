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

export interface AdminSessionsResponse {
  sessions: unknown[];
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

  getSessions: async (): Promise<AdminSessionsResponse> => {
    const res = await fetch(getApiUrl("/auth/admin/sessions"), {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch sessions");
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
