const API_BASE = '';

interface ApiOptions {
  method?: string;
  body?: any;
  signal?: AbortSignal;
}

export async function api<T = any>(path: string, options: ApiOptions = {}): Promise<T> {
  const token = localStorage.getItem('tp_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json; charset=utf-8',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method || 'GET',
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });

  if (response.status === 401) {
    throw new Error('请先登录');
  }

  if (!response.ok) {
    const text = await response.text();
    try {
      const data = JSON.parse(text);
      throw new Error(data.error?.message || `请求失败 (${response.status})`);
    } catch {
      if (text.startsWith('{')) throw new Error(`请求失败 (${response.status})`);
      throw new Error(text || `请求失败 (${response.status})`);
    }
  }

  const text = await response.text();
  if (!text) return {} as T;
  return JSON.parse(text);
}
