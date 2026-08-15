const API_BASE = "/api";

export interface TripletUI {
  alias: string;
  provider: string;
  model: string;
  api_key: string;
  has_key: boolean;
}

export interface RuleUI {
  when: "rate_limit" | "server_error";
  use: string[];
}

export interface OperationConfigUI {
  order: string[];
  rules: RuleUI[];
}

export interface LLMConfigUI {
  version: number;
  name: string;
  triplets: TripletUI[];
  chat: OperationConfigUI;
  memory: OperationConfigUI;
}

export interface ProviderInfo {
  id: string;
  name: string;
  key_url: string;
}

export interface ModelInfo {
  id: string;
  provider: string;
  label: string;
  tier: "premium" | "standard" | "budget" | "free";
  recommended: "chat" | "memory" | "either";
  supports_images: boolean;
  price_in: string;
  price_out: string;
  price_note: string;
}

export interface CatalogInfo {
  providers: ProviderInfo[];
  models: ModelInfo[];
}

export interface PingResult {
  alias: string;
  provider: string;
  model: string;
  ok: boolean;
  error: string | null;
  latency_ms: number | null;
  kind?: string;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export async function getLlmConfig(): Promise<LLMConfigUI> {
  return req<LLMConfigUI>("/settings/config");
}

export async function saveLlmConfig(config: LLMConfigUI): Promise<LLMConfigUI> {
  return req<LLMConfigUI>("/settings/config", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export async function getCatalog(): Promise<CatalogInfo> {
  return req<CatalogInfo>("/settings/catalog");
}

export async function exportLlmConfig(): Promise<string> {
  const data = await req<{ yaml: string }>("/settings/config/export", {
    method: "POST",
  });
  return data.yaml;
}

export async function importLlmConfig(yaml: string): Promise<LLMConfigUI> {
  return req<LLMConfigUI>("/settings/config/import", {
    method: "POST",
    body: JSON.stringify({ yaml }),
  });
}

export async function testLlmConfig(config?: LLMConfigUI): Promise<PingResult[]> {
  const data = await req<{ results: PingResult[] }>("/settings/config/test", {
    method: "POST",
    body: config ? JSON.stringify(config) : undefined,
  });
  return data.results;
}
