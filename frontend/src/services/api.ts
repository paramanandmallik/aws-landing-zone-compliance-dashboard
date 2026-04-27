import { getIdToken } from './auth';

const BASE_URL = import.meta.env.REACT_APP_API_URL || '';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

type ErrorCallback = (status: number, message: string) => void;

let _onError: ErrorCallback | null = null;

/** Set a global error callback (e.g. from ToastProvider). */
export function setApiErrorHandler(cb: ErrorCallback | null) {
  _onError = cb;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = await getIdToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    window.location.href = '/login';
    throw new ApiError(401, 'Unauthorized');
  }
  if (res.status === 403) {
    _onError?.(403, 'Forbidden — you do not have permission for this action');
    throw new ApiError(403, 'Forbidden');
  }
  if (res.status >= 500) {
    _onError?.(res.status, 'Server error — please try again later');
    throw new ApiError(res.status, 'Server error');
  }
  if (!res.ok) {
    const text = await res.text().catch(() => 'Request failed');
    _onError?.(res.status, text);
    throw new ApiError(res.status, text);
  }

  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
};

export { ApiError };
