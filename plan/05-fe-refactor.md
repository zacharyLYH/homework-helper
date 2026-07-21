# Stage 05: Frontend - Refactoring

**Sequence: 5 of 7**
**Scope: `frontend/src/` — all TypeScript/React files**
**Goal: Remove dead code, extract repeated patterns, reduce ChatPage complexity**

---

## Why This Stage Fifth

Frontend refactoring comes after backend because (a) backend is the source of truth for API contracts, and (b) the FE refactor is lighter — the FE is already reasonably well-structured. Main targets: dead npm dependencies, unused UI component, duplicated Chat interface definitions, and the massive `handleSubmit` in ChatPage.

---

## Guidelines (STRICT)

1. **DO NOT change any API endpoint paths, request shapes, or response shapes.** Backend is the source of truth.
2. **DO NOT remove `@assistant-ui/react` or `@assistant-ui/react-ai-sdk` from package.json yet** — we'll do that as a separate cleanup step since it requires npm install.
3. **DO NOT change component props interfaces** that are shared between components (e.g., SidebarProps).
4. **Verify: `cd frontend && npx tsc --noEmit`**

---

## Work Items

### 5.1: Remove unused `progress.tsx`

The file `frontend/src/components/ui/progress.tsx` is never imported anywhere. Delete it:

```bash
rm /Users/zac/Desktop/homework-helper/frontend/src/components/ui/progress.tsx
```

### 5.2: Remove unused npm dependencies

Run:
```bash
cd /Users/zac/Desktop/homework-helper/frontend
npm uninstall @assistant-ui/react @assistant-ui/react-ai-sdk
```

These packages are in `package.json` but never imported in any source file.

### 5.3: Deduplicate Chat interface

The `Chat` interface is defined in `api.ts` (line 159) AND re-defined in `Sidebar.tsx` (line 31). They're identical. The Sidebar should import from `api.ts`.

**In `Sidebar.tsx`:**
1. Remove the local `Chat` interface (lines 31-42)
2. Add `Chat` to the import from `@/lib/api`:
   ```typescript
   import { createSubject, createChat, type Subject, type Chat } from "@/lib/api";
   ```

**In `ChatPage.tsx`:**
- Already imports `Chat as ChatType` from `@/lib/api` — no change needed.

### 5.4: Extract `sendChatStream` callback object

`sendChatStream` in `api.ts` takes 9 positional parameters. This is hard to read at the call site (ChatPage line 129-199). Convert to an options object:

**In `api.ts`, change `sendChatStream` to:**

```typescript
export interface ChatStreamOptions {
  message: string;
  chatId?: number;
  image?: string;
  imageMediaType?: string;
  messages?: ChatMessage[];
  onToken: (content: string) => void;
  onDone: (usage?: TokenUsage) => void;
  onError: (error: string) => void;
  onTitle?: (title: string) => void;
}

export function sendChatStream(options: ChatStreamOptions): AbortController {
  const { message, chatId, image, imageMediaType, messages, onToken, onDone, onError, onTitle } = options;
  // ... rest of implementation unchanged
}
```

**In `ChatPage.tsx`, update the call site:**

```typescript
abortRef.current = sendChatStream({
  message: msg || "What's in this image?",
  chatId: selectedChatId,
  image: sentImage || undefined,
  imageMediaType: sentMediaType || undefined,
  messages: historyMessages,
  onToken: (token) => { /* ... */ },
  onDone: (usage) => { /* ... */ },
  onError: (err) => { /* ... */ },
  onTitle: (title) => { /* ... */ },
});
```

### 5.5: Extract ChatPage helper functions

`ChatPage.tsx` has a 90-line `handleSubmit` function (lines 113-200). Extract the callback bodies into named functions for readability:

```typescript
// Token streaming callback
const handleToken = useCallback((token: string) => {
  setMessages((prev) => {
    const updated = [...prev];
    const last = updated[updated.length - 1];
    if (last.role === "assistant") {
      last.content += token;
    }
    return [...updated];
  });
}, []);

// Stream completion callback
const handleStreamDone = useCallback((usage?: TokenUsage) => {
  if (usage) {
    setCurrentMessageUsage(usage);
    if (selectedChatId) {
      updateChatTokens(selectedChatId, usage);
    }
  }
  setStreaming(false);
}, [selectedChatId]);

// Token update helper (extracted from the nested callback)
const updateChatTokens = useCallback((chatId: number, usage: TokenUsage) => {
  setChatsBySubject((prev) => {
    const subjectId = subjects.find((s) => prev[s.id]?.some((c) => c.id === chatId))?.id;
    if (subjectId && prev[subjectId]) {
      return {
        ...prev,
        [subjectId]: prev[subjectId].map((c) =>
          c.id === chatId
            ? { ...c, input_tokens: c.input_tokens + usage.input_tokens, output_tokens: c.output_tokens + usage.output_tokens, total_tokens: c.total_tokens + usage.total_tokens }
            : c
        ),
      };
    }
    return prev;
  });
}, [subjects]);
```

**Also extract `handleStreamError`:**

```typescript
const handleStreamError = useCallback((err: string) => {
  setMessages((prev) => {
    const updated = [...prev];
    const last = updated[updated.length - 1];
    if (last.role === "assistant") {
      last.content = last.content || `Error: ${err}`;
    }
    return updated;
  });
  setStreaming(false);
}, []);
```

**And `handleTitleUpdate`:**

```typescript
const handleTitleUpdate = useCallback((title: string) => {
  if (!selectedChatId) return;
  setChatsBySubject((prev) => {
    const subjectId = subjects.find((s) => prev[s.id]?.some((c) => c.id === selectedChatId))?.id;
    if (subjectId && prev[subjectId]) {
      return {
        ...prev,
        [subjectId]: prev[subjectId].map((c) =>
          c.id === selectedChatId ? { ...c, title } : c
        ),
      };
    }
    return prev;
  });
}, [selectedChatId, subjects]);
```

### 5.6: Verify TypeScript compilation

Run:
```bash
cd /Users/zac/Desktop/homework-helper/frontend
npx tsc --noEmit
```

Must pass with zero errors.

### 5.7: Verify build

Run:
```bash
cd /Users/zac/Desktop/homework-helper/frontend
npm run build
```

Must succeed.

---

## Expected Outcome

- `progress.tsx` removed (31 lines)
- `@assistant-ui/react` and `@assistant-ui/react-ai-sdk` removed from package.json
- `Chat` interface defined once in `api.ts`, imported everywhere else
- `sendChatStream` uses options object instead of 9 positional params
- `ChatPage.handleSubmit` decomposed into 5 named callback functions
- Zero TypeScript errors
- Zero behavior changes
