declare const VITE_API_BASE_URL: string;
declare const TOKEN: string;

const AUTH_TOKEN_KEY = "qwenpaw_auth_token";
const USERNAME_KEY = "openspider_username";
const USER_ROLE_KEY = "openspider_user_role";

// Cached username promise to avoid concurrent /auth/verify calls
let _usernamePromise: Promise<string> | null = null;
let _userRolePromise: Promise<string> | null = null;

/**
 * Get the full API URL with /api prefix
 * @param path - API path (e.g., "/models", "/skills")
 * @returns Full API URL (e.g., "http://localhost:8088/api/models" or "/api/models")
 */
export function getApiUrl(path: string): string {
  const base = VITE_API_BASE_URL || "";
  const apiPrefix = "/api";
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${apiPrefix}${normalizedPath}`;
}

/**
 * Get the API token - checks localStorage first (auth login),
 * then falls back to the build-time TOKEN constant.
 * @returns API token string or empty string
 */
export function getApiToken(): string {
  const stored = localStorage.getItem(AUTH_TOKEN_KEY);
  if (stored) return stored;
  return typeof TOKEN !== "undefined" ? TOKEN : "";
}

/**
 * Store the auth token in localStorage after login.
 */
export function setAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

/**
 * Remove the auth token from localStorage (logout / 401).
 */
export function clearAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

// ---------------------------------------------------------------------------
// Username helpers (used to scope knowledge bases per user)
// ---------------------------------------------------------------------------

/** Decode the username from a base64url-encoded token payload. */
function _decodeUsernameFromToken(token: string): string | null {
  try {
    const parts = token.split(".");
    if (parts.length < 1) return null;
    // Token format: base64url(JSON).hex_sig
    const raw = atob(parts[0].replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(raw) as { sub?: string };
    return payload.sub || null;
  } catch {
    return null;
  }
}

/**
 * Get the current authenticated username.
 *
 * Resolution order:
 * 1. localStorage ``openspider_username`` (set on login)
 * 2. Decode from the auth token's base64url payload (``sub`` claim)
 * 3. Fetch ``/api/auth/verify`` (cached per page load)
 *
 * @returns Username string, or empty string if not authenticated
 */
export async function getCurrentUsername(): Promise<string> {
  // 1. localStorage
  const stored = localStorage.getItem(USERNAME_KEY);
  if (stored) return stored;

  // 2. Decode from token
  const token = getApiToken();
  if (token) {
    const fromToken = _decodeUsernameFromToken(token);
    if (fromToken) {
      localStorage.setItem(USERNAME_KEY, fromToken);
      return fromToken;
    }
  }

  // 3. Fetch /auth/verify (deduplicate concurrent calls)
  if (!_usernamePromise) {
    _usernamePromise = (async () => {
      try {
        const res = await fetch(getApiUrl("/auth/verify"), {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const data = (await res.json()) as {
            username?: string;
          };
          if (data.username) {
            localStorage.setItem(USERNAME_KEY, data.username);
            return data.username;
          }
        }
      } catch {
        // Silently fail — caller handles empty string
      }
      return "";
    })();
  }
  return _usernamePromise;
}

/**
 * Store the current username in localStorage (called after login/register).
 */
export function setCurrentUsername(username: string): void {
  localStorage.setItem(USERNAME_KEY, username);
}

/** Decode the role from the auth token's base64url payload (``role`` claim). */
function _decodeRoleFromToken(token: string): string | null {
  try {
    const parts = token.split(".");
    if (parts.length < 1) return null;
    const raw = atob(parts[0].replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(raw) as { role?: string };
    return payload.role || null;
  } catch {
    return null;
  }
}

/**
 * Get the current authenticated user's role.
 *
 * Resolution order:
 * 1. localStorage ``openspider_user_role`` (set on login)
 * 2. Decode from the auth token's base64url payload (``role`` claim)
 * 3. Fetch ``/api/auth/verify`` (cached per page load)
 *
 * @returns ``"admin"``, ``"user"``, or empty string if not authenticated
 */
export async function getCurrentUserRole(): Promise<string> {
  // 1. localStorage
  const stored = localStorage.getItem(USER_ROLE_KEY);
  if (stored) return stored;

  // 2. Decode from token
  const token = getApiToken();
  if (token) {
    const fromToken = _decodeRoleFromToken(token);
    if (fromToken) {
      localStorage.setItem(USER_ROLE_KEY, fromToken);
      return fromToken;
    }
  }

  // 3. Fetch /auth/verify (deduplicate concurrent calls)
  if (!_userRolePromise) {
    _userRolePromise = (async () => {
      try {
        const res = await fetch(getApiUrl("/auth/verify"), {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const data = (await res.json()) as {
            role?: string;
          };
          if (data.role) {
            localStorage.setItem(USER_ROLE_KEY, data.role);
            return data.role;
          }
        }
      } catch {
        // Silently fail — caller handles empty string
      }
      return "";
    })();
  }
  return _userRolePromise;
}

/**
 * Store the current user role in localStorage (called after login/register).
 */
export function setCurrentUserRole(role: string): void {
  localStorage.setItem(USER_ROLE_KEY, role);
}
