import type { Page } from "@playwright/test";
import type { TokenUsage, ToolCallInfo, ChatStreamRequest } from "../../src/lib/api";
import type { WhiteboardElement } from "../../src/lib/whiteboard";

// Wire contract for one SSE event emitted by /api/chat/stream.
export type ChatStreamEvent =
  | { type: "token"; content: string }
  | { type: "title"; content: string }
  | ({ type: "tool_call" } & ToolCallInfo)
  | { type: "drawing"; elements: WhiteboardElement[] }
  | { type: "done"; usage?: TokenUsage }
  | { type: "error"; content: string };

const line = (event: ChatStreamEvent) => `data: ${JSON.stringify(event)}\n`;

export const sseEvent = {
  token: (content: string): ChatStreamEvent => ({ type: "token", content }),
  title: (content: string): ChatStreamEvent => ({ type: "title", content }),
  toolCall: (id: string, name: string, args: Record<string, unknown>): ChatStreamEvent => ({
    type: "tool_call",
    id,
    name,
    args,
  }),
  drawing: (elements: WhiteboardElement[]): ChatStreamEvent => ({ type: "drawing", elements }),
  done: (usage: Partial<TokenUsage> = {}): ChatStreamEvent => ({
    type: "done",
    usage: { input_tokens: 10, output_tokens: 4, total_tokens: 14, ...usage },
  }),
  error: (content: string): ChatStreamEvent => ({ type: "error", content }),
};

export interface StreamSpec {
  chunks: { data: string; delay?: number }[];
}

// A stream is a sequence of events; add an optional `delay` to a part to hold
// delivery of that chunk `delay` ms after the previous one.
export type StreamPart = ChatStreamEvent | { event: ChatStreamEvent; delay?: number };

export function sseStream(parts: StreamPart[]): StreamSpec {
  const chunks: { data: string; delay?: number }[] = [];
  let buf = "";
  let bufDelay: number | undefined;
  const flush = () => {
    if (!buf) return;
    chunks.push({ data: buf, delay: bufDelay });
    buf = "";
    bufDelay = undefined;
  };
  for (const part of parts) {
    const delayed = !("type" in part);
    const event = delayed
      ? (part as { event: ChatStreamEvent; delay?: number }).event
      : (part as ChatStreamEvent);
    const delay = delayed ? (part as { delay?: number }).delay : undefined;
    if (delay !== undefined && buf) flush();
    buf += line(event);
    if (delay !== undefined) bufDelay = delay;
  }
  flush();
  return { chunks };
}

export const DEFAULT_STREAM: StreamSpec = sseStream([
  sseEvent.token("The answer is 4."),
  sseEvent.done(),
]);

// ---------------------------------------------------------------------------
// LLM settings fixtures. The default config has chat + memory wired so the
// chat page stays usable in every existing test; settings tests swap it via
// `stubLlmConfig`. PUTs are persisted to localStorage so reloads behave like a
// real backend.

// NOTE: everything below is consumed either as a serialized init-script
// argument or inside `mockBackendClient`, which is itself serialized into the
// browser. Never reference these module-scope consts from inside a function
// Playwright serializes — inline the strings or pass them via the `config`
// argument, exactly like `defaultSpec` already does.

export const EMPTY_LLM_CONFIG = {
  version: 1,
  name: "My Config",
  triplets: [],
  chat: { order: [], rules: [] },
  memory: { order: [], rules: [] },
};

export const DEFAULT_LLM_CONFIG = {
  version: 1,
  name: "My Config",
  triplets: [
    { alias: "flash", provider: "gemini", model: "gemini-3.7-flash", api_key: "sk-f****cret", has_key: true },
  ],
  chat: { order: ["flash"], rules: [] },
  memory: { order: ["flash"], rules: [] },
};

export const CATALOG = {
  providers: [
    { id: "gemini", name: "Google Gemini", key_url: "https://aistudio.google.com/apikey" },
    { id: "openrouter", name: "OpenRouter", key_url: "https://openrouter.ai/keys" },
    { id: "openai", name: "OpenAI", key_url: "https://platform.openai.com/api-keys" },
    { id: "anthropic", name: "Anthropic", key_url: "https://console.anthropic.com/settings/keys" },
  ],
  models: [
    { id: "gemini-3.1-pro-preview", provider: "gemini", label: "Gemini 3.1 Pro (Preview)", tier: "premium", recommended: "chat", supports_images: true, price_in: "$2.00", price_out: "$12.00", price_note: "exact list price" },
    { id: "gemini-3.7-flash", provider: "gemini", label: "Gemini 3.7 Flash", tier: "standard", recommended: "chat", supports_images: true, price_in: "$0.75", price_out: "$3.75", price_note: "intro price" },
    { id: "deepseek/deepseek-v4-flash-0731", provider: "openrouter", label: "DeepSeek V4 Flash (open)", tier: "budget", recommended: "either", supports_images: true, price_in: "~$0.08", price_out: "~$0.16", price_note: "varies by host" },
    { id: "openai/gpt-5.6-luna", provider: "openrouter", label: "GPT-5.6 Luna", tier: "budget", recommended: "either", supports_images: true, price_in: "$0.10", price_out: "$0.60", price_note: "varies by host" },
    { id: "xiaomi/mimo-v2.5", provider: "openrouter", label: "MiMo-V2.5 (open)", tier: "budget", recommended: "either", supports_images: true, price_in: "$0.14", price_out: "$0.28", price_note: "varies by host" },
    { id: "qwen/qwen3-vl-32b-instruct", provider: "openrouter", label: "Qwen3-VL 32B (open)", tier: "budget", recommended: "either", supports_images: true, price_in: "~$0.10", price_out: "~$0.42", price_note: "varies by host" },
    { id: "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", provider: "openrouter", label: "NVIDIA Nemotron 3 Nano Omni (free)", tier: "free", recommended: "either", supports_images: true, price_in: "$0", price_out: "$0", price_note: "free" },
    { id: "gemini-3.5-flash-lite", provider: "gemini", label: "Gemini 3.5 Flash-Lite", tier: "budget", recommended: "memory", supports_images: true, price_in: "$0.30", price_out: "$2.50", price_note: "exact list price" },
    { id: "qwen/qwen3-14b", provider: "openrouter", label: "Qwen3 14B (open, text)", tier: "budget", recommended: "memory", supports_images: false, price_in: "~$0.10", price_out: "~$0.25", price_note: "varies by host" },
    { id: "openrouter/free", provider: "openrouter", label: "OpenRouter Free", tier: "free", recommended: "memory", supports_images: false, price_in: "$0", price_out: "$0", price_note: "free" },
  ],
};

// Applies `cfg` to every subsequent navigation in this page: the mock serves it
// for /api/settings/config instead of the wired default. The window key and
// storage key are inlined on purpose — this script is serialized into the page.
export async function stubLlmConfig(page: Page, cfg: unknown): Promise<void> {
  await page.addInitScript((c) => {
    try {
      window.localStorage.removeItem("__hh_llm_config_storage");
    } catch {
      /* ignore */
    }
    (window as any)["__hh_llm_config"] = c;
  }, cfg);
}

// ---------------------------------------------------------------------------
// The one backend mock. Installed as an init script (so it survives
// navigation) by `initMockBackend`, it overrides window.fetch with a mock that
// serves every /api endpoint from canned JSON. page.route is deliberately not
// used for these: the app _and_ the stream go through a fetch override, so
// there is a single place where the backend lives.

export interface MockBackendConfig {
  // true → /api/auth/me + refresh return 200, false → 401 (app logs out).
  auth: boolean;
  // Initial streamed reply for /api/chat/stream.
  defaultSpec: StreamSpec;
  // Defaults served for /api/settings/*. Wired (chat + memory) by default so
  // existing chat tests keep working; settings tests swap via stubLlmConfig.
  defaultLlmConfig?: unknown;
  catalog?: unknown;
}

const STREAM_KEY = "__hh_stream_spec";
const CAPTURE_KEY = "__hh_stream_capture";

// Runs in the browser; reads/writes per-document state on `window`, so tests
// can swap the stream with `stubStream`/`captureStream` after navigating.
export const mockBackendClient = (config: MockBackendConfig) => {
  const enc = new TextEncoder();
  const w = window as any;
  const original = w["__hh_orig_fetch"] ?? window.fetch;
  w["__hh_orig_fetch"] = original;

  const handle = (path: string, method: string, payload?: unknown) => {
    const has = (s: string) => path.includes(s);

    // Keys are inlined on purpose — this handler is serialized into the page.
    const storedLlmConfig =
      w["__hh_llm_config"] ??
      (() => {
        try {
          const raw = localStorage.getItem("__hh_llm_config_storage");
          return raw ? JSON.parse(raw) : null;
        } catch {
          return null;
        }
      })() ??
      config.defaultLlmConfig;
    if (has("/api/settings/catalog")) {
      return { status: 200, body: config.catalog ?? { providers: [], models: [] } };
    }
    if (has("/api/settings/config")) {
      if (method === "GET") return { status: 200, body: storedLlmConfig };
      if (method === "PUT") {
        const aliases = ((payload as any)?.triplets ?? []).map((t: any) => t.alias);
        if (new Set(aliases).size !== aliases.length) {
          // Mirrors the real backend rejecting duplicate triplet aliases.
          return { status: 422, body: { detail: `Duplicate triplet aliases: ${aliases.join(", ")}` } };
        }
        w["__hh_llm_config"] = payload;
        try {
          localStorage.setItem("__hh_llm_config_storage", JSON.stringify(payload));
        } catch {
          /* ignore */
        }
        return { status: 200, body: payload };
      }
    }
    if (has("/api/settings/config/test")) {
      // A key containing "bad" simulates an invalid key → failed ping.
      const cfg = (payload as any) ?? storedLlmConfig;
      const results = (cfg?.triplets ?? []).map((t: any) => {
        const bad = typeof t.api_key === "string" && t.api_key.includes("bad");
        return {
          alias: t.alias,
          provider: t.provider,
          model: t.model,
          ok: !bad,
          error: bad ? "HTTP 401: invalid api key" : null,
          latency_ms: bad ? null : 42,
        };
      });
      return { status: 200, body: { results } };
    }

    if (has("/api/auth/me")) {
      return config.auth
        ? { status: 200, body: { id: 1, email: "test@example.com" } }
        : { status: 401, body: { detail: "Unauthorized" } };
    }
    if (has("/api/auth/refresh")) {
      return config.auth ? { status: 200, body: { access_token: "mock" } } : { status: 401, body: { detail: "Unauthorized" } };
    }
    if (has("/api/auth/verify")) {
      return { status: 200, body: { access_token: "mock", user: { id: 1, email: "test@example.com" } } };
    }
    if (has("/api/auth/request-code")) {
      return { status: 200, body: { message: "code sent" } };
    }
    if (has("/api/auth/logout")) {
      return { status: 204, body: null };
    }
    if (has("/api/subjects")) {
      if (method === "POST") {
        const name = new URL(path, w.location.origin).searchParams.get("name") ?? "New Subject";
        return { status: 200, body: { id: 3, user_id: 1, name, created_at: "2026-01-03T00:00:00Z" } };
      }
      return {
        status: 200,
        body: [
          { id: 1, user_id: 1, name: "Mathematics", created_at: "2026-01-01T00:00:00Z", chats: [{ id: 10, title: "Algebra review", total_tokens: 42 }] },
          { id: 2, user_id: 1, name: "Physics", created_at: "2026-01-02T00:00:00Z", chats: [] },
        ],
      };
    }
    if (has("/messages")) {
      return {
        status: 200,
        body: [
          { id: 100, chat_id: 10, role: "user", content: "How do I solve x + 2 = 5?", token_count: 8, created_at: "2026-01-01T00:00:00Z" },
          { id: 101, chat_id: 10, role: "assistant", content: "Subtract 2 from both sides, so x = 3.", token_count: 12, created_at: "2026-01-01T00:00:01Z" },
        ],
      };
    }
    if (has("/api/chats")) {
      if (method === "POST") {
        const url = new URL(path, w.location.origin);
        return {
          status: 200,
          body: {
            id: 11,
            subject_id: Number(url.searchParams.get("subject_id")),
            title: url.searchParams.get("title") ?? "New Chat",
            created_at: "2026-01-03T00:00:00Z",
            updated_at: "2026-01-03T00:00:00Z",
          },
        };
      }
      return {
        status: 200,
        body: [
          { id: 10, subject_id: 1, user_id: 1, title: "Algebra review", total_tokens: 42, input_tokens: 20, output_tokens: 22, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
        ],
      };
    }
    return null;
  };

  const json = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

  const streamBody = () =>
    new ReadableStream({
      start(controller) {
        const spec = w["__hh_stream_spec"] ?? config.defaultSpec;
        let i = 0;
        const pump = () => {
          if (i >= spec.chunks.length) {
            controller.close();
            return;
          }
          const chunk = spec.chunks[i++];
          const deliver = () => {
            controller.enqueue(enc.encode(chunk.data));
            pump();
          };
          if (chunk.delay) setTimeout(deliver, chunk.delay);
          else deliver();
        };
        pump();
      },
    });

  w.fetch = (input: any, init?: any) => {
    const path = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    let payload: unknown;
    if (typeof init?.body === "string") {
      try {
        payload = JSON.parse(init.body);
      } catch {
        payload = undefined;
      }
    }
    if (path.includes("/api/chat/stream")) {
      if (Array.isArray(w["__hh_stream_capture"])) {
        const raw = init && typeof init.body === "string" ? init.body : "{}";
        try {
          w["__hh_stream_capture"].push(JSON.parse(raw));
        } catch {
          w["__hh_stream_capture"].push({});
        }
      }
      return Promise.resolve(
        new Response(streamBody(), { status: 200, headers: { "content-type": "text/event-stream" } }),
      );
    }
    const hit = handle(path, method, payload);
    if (hit) return Promise.resolve(hit.status === 204 ? new Response(null, { status: 204 }) : json(hit.status, hit.body));
    return original(input, init);
  };
};

export async function initMockBackend(page: Page, config: MockBackendConfig): Promise<void> {
  await page.addInitScript(mockBackendClient, config);
}

export interface CapturedStream {
  all: () => Promise<ChatStreamRequest[]>;
}

// Swaps the streamed reply for `spec`. Must be called after the page has
// navigated (it writes to the current document's mock state).
export async function stubStream(page: Page, spec: StreamSpec = DEFAULT_STREAM): Promise<void> {
  await page.evaluate(([key, s]) => {
    const w = window as any;
    w[key] = s;
    w["__hh_stream_capture"] = undefined;
  }, [STREAM_KEY, spec] as const);
}

// Swaps in `spec` and starts recording every /api/chat/stream request's body.
export async function captureStream(page: Page, spec: StreamSpec = DEFAULT_STREAM): Promise<CapturedStream> {
  await page.evaluate(([key, s]) => {
    const w = window as any;
    w[key] = s;
    w["__hh_stream_capture"] = [];
  }, [STREAM_KEY, spec] as const);
  return {
    all: () => page.evaluate((k) => (window as any)[k] ?? [], CAPTURE_KEY),
  };
}