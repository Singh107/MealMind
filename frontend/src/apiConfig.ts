// CRA embeds this public value at startup/build time. Never put provider keys here.
export function normalizeApiBase(value?: string): string {
  return (value?.trim() || 'http://127.0.0.1:8000').replace(/\/+$/, '');
}

export const API_BASE_URL = normalizeApiBase(process.env.REACT_APP_API_URL);
export const apiUrl = (path: string) => `${API_BASE_URL}/${path.replace(/^\/+/, '')}`;
