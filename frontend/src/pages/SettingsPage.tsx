import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Download,
  Image as ImageIcon,
  Info as InfoIcon,
  Loader2,
  LogOut,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  getCatalog,
  getLlmConfig,
  saveLlmConfig,
  exportLlmConfig,
  importLlmConfig,
  testLlmConfig,
  type CatalogInfo,
  type LLMConfigUI,
  type ModelInfo,
  type PingResult,
  type TripletUI,
  type OperationConfigUI,
  type RuleUI,
} from "@/lib/settings";

const ROUTING_REASONS: { value: "rate_limit" | "server_error"; label: string; tip: string }[] = [
  { value: "rate_limit", label: "On 429", tip: "Rate limited. Fall back to a different model." },
  { value: "server_error", label: "On 5xx", tip: "Server error or timeout. Fall back to a different model." },
];

const EMPTY_CONFIG: LLMConfigUI = {
  version: 1,
  name: "My Config",
  triplets: [],
  chat: { order: [], rules: [] },
  memory: { order: [], rules: [] },
};

type SaveState = "idle" | "saving" | "saved" | "error";

type TripletTestStatus =
  | { state: "idle" }
  | { state: "testing" }
  | { state: "ok"; latencyMs: number | null }
  | { state: "failed"; error: string };

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [config, setConfig] = useState<LLMConfigUI>(EMPTY_CONFIG);
  const [catalog, setCatalog] = useState<CatalogInfo>({ providers: [], models: [] });
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState(0);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<PingResult[] | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importYaml, setImportYaml] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [form, setForm] = useState({ provider: "gemini", model: "", alias: "", api_key: "" });
  const lastSavedRef = useRef<string | null>(null);
  const [tripletTests, setTripletTests] = useState<Record<string, TripletTestStatus>>({});

  // --- load ---

  useEffect(() => {
    Promise.all([getLlmConfig(), getCatalog()])
      .then(([cfg, cat]) => {
        setConfig(cfg);
        setCatalog(cat);
        lastSavedRef.current = JSON.stringify(cfg);
      })
      .catch((e) => setMessage({ kind: "err", text: String(e.message || e) }))
      .finally(() => setLoading(false));
  }, []);

  // --- auto-save (debounced) ---

  useEffect(() => {
    if (lastSavedRef.current === null) return; // not loaded yet
    const serialized = JSON.stringify(config);
    if (serialized === lastSavedRef.current) return;
    setSaveState("saving");
    const t = setTimeout(() => {
      saveLlmConfig(config)
        .then(() => {
          lastSavedRef.current = serialized;
          setSaveState("saved");
        })
        .catch((e) => {
          setSaveState("error");
          setMessage({ kind: "err", text: String((e as Error).message || e) });
        });
    }, 800);
    return () => clearTimeout(t);
  }, [config]);

  const modelsDone = config.triplets.length > 0;
  const chatDone = config.chat.order.length > 0;
  const memoryDone = config.memory.order.length > 0;
  const maxStep = !modelsDone ? 0 : !chatDone ? 1 : !memoryDone ? 2 : 3;

  // Ping a model the moment its profile is created/edited so users know
  // immediately whether the key + model combination works.
  const testTriplet = useCallback(async (cfg: LLMConfigUI, alias: string) => {
    setTripletTests((prev) => ({ ...prev, [alias]: { state: "testing" } }));
    try {
      const results = await testLlmConfig(cfg);
      const result = results.find((r) => r.alias === alias);
      if (result && result.ok) {
        setTripletTests((prev) => ({ ...prev, [alias]: { state: "ok", latencyMs: result.latency_ms } }));
      } else {
        setTripletTests((prev) => ({ ...prev, [alias]: { state: "failed", error: result?.error ?? "No response" } }));
      }
    } catch (e) {
      setTripletTests((prev) => ({ ...prev, [alias]: { state: "failed", error: String((e as Error).message || e) } }));
    }
  }, []);

  // --- triplet editing ---

  const removeTriplet = useCallback((i: number) => {
    const removed = config.triplets[i];
    if (!removed) return;
    setTripletTests((prev) => {
      const next = { ...prev };
      delete next[removed.alias];
      return next;
    });
    setConfig((prev) => {
      const triplets = prev.triplets.filter((_, idx) => idx !== i);
      return {
        ...prev,
        triplets,
        chat: stripAlias(prev.chat, removed.alias),
        memory: stripAlias(prev.memory, removed.alias),
      };
    });
  }, [config]);

  // --- add/edit model dialog ---

  const openAdd = () => {
    setForm({ provider: "gemini", model: "", alias: "", api_key: "" });
    setEditingIndex(null);
    setDialogOpen(true);
  };

  const openEdit = (i: number) => {
    const t = config.triplets[i];
    if (!t) return;
    setForm({ provider: t.provider, model: t.model, alias: t.alias, api_key: "" });
    setEditingIndex(i);
    setDialogOpen(true);
  };

  const submitDialog = () => {
    const alias = form.alias.trim();
    if (!alias || !form.model) return;
    let next: LLMConfigUI;
    if (editingIndex === null) {
      const triplet: TripletUI = {
        alias,
        provider: form.provider,
        model: form.model,
        api_key: form.api_key,
        has_key: Boolean(form.api_key),
      };
      next = { ...config, triplets: [...config.triplets, triplet] };
    } else {
      const idx = editingIndex;
      const old = config.triplets[idx];
      if (!old) return;
      const updated = {
        ...old,
        alias,
        provider: form.provider,
        model: form.model,
        api_key: form.api_key || old.api_key,
        has_key: old.has_key || Boolean(form.api_key),
      };
      const triplets = config.triplets.map((t, i) => (i === idx ? updated : t));
      next = alias !== old.alias ? replaceAlias(config, old.alias, alias, triplets) : { ...config, triplets };
    }
    setConfig(next);
    setDialogOpen(false);
    void testTriplet(next, alias);
  };

  // --- order + rules edits ---

  const patchOperation = useCallback(
    (section: "chat" | "memory", patch: Partial<OperationConfigUI>) => {
      setConfig((prev) => ({ ...prev, [section]: { ...prev[section], ...patch } }));
    },
    [],
  );

  const moveInOrder = useCallback((section: "chat" | "memory", idx: number, dir: -1 | 1) => {
    setConfig((prev) => {
      const order = [...prev[section].order];
      const j = idx + dir;
      if (j < 0 || j >= order.length) return prev;
      [order[idx], order[j]] = [order[j], order[idx]];
      return { ...prev, [section]: { ...prev[section], order } };
    });
  }, []);

  const toggleRuleAlias = useCallback(
    (section: "chat" | "memory", when: "rate_limit" | "server_error", alias: string) => {
      setConfig((prev) => {
        const rules = prev[section].rules.map((r) =>
          r.when === when
            ? { ...r, use: r.use.includes(alias) ? r.use.filter((a) => a !== alias) : [...r.use, alias] }
            : r,
        );
        if (!rules.some((r) => r.when === when)) {
          rules.push({ when, use: [alias] });
        }
        return { ...prev, [section]: { ...prev[section], rules } };
      });
    },
    [],
  );

  // --- actions ---

  const handleTest = async () => {
    setTesting(true);
    setTestResults(null);
    setMessage(null);
    try {
      await saveLlmConfig(config); // flush any pending edits
      lastSavedRef.current = JSON.stringify(config);
      setSaveState("saved");
      const results = await testLlmConfig();
      setTestResults(results);
      const failed = results.filter((r) => !r.ok);
      if (failed.length > 0) {
        setMessage({ kind: "err", text: `${failed.length}/${results.length} failed.` });
      }
    } catch (e) {
      setMessage({ kind: "err", text: String((e as Error).message || e) });
    } finally {
      setTesting(false);
    }
  };

  const handleExport = async () => {
    setMessage(null);
    try {
      const yaml = await exportLlmConfig();
      const blob = new Blob([yaml], { type: "text/yaml" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "llm-config.yaml";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setMessage({ kind: "err", text: String((e as Error).message || e) });
    }
  };

  const handleImport = async () => {
    setMessage(null);
    try {
      const parsed = await importLlmConfig(importYaml);
      setConfig(parsed);
      setImportOpen(false);
      setImportYaml("");
      setMessage({ kind: "ok", text: "Keys stripped — re-enter them." });
    } catch (e) {
      setMessage({ kind: "err", text: String((e as Error).message || e) });
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen text-muted-foreground">
        Loading...
      </div>
    );
  }

  const aliases = config.triplets.map((t) => t.alias);
  const editingTriplet = editingIndex !== null ? config.triplets[editingIndex] : null;

  return (
    <TooltipProvider>
      <div className="flex h-svh flex-col bg-background">
        <header className="flex items-center justify-between px-3 sm:px-4 py-3 border-b border-border gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate("/chat")}
              title="Back to chat"
              className="cursor-pointer"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <h1 className="text-sm font-semibold truncate shrink-0">Settings</h1>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <SaveIndicator state={saveState} />
            <span className="hidden sm:inline text-sm text-muted-foreground truncate max-w-40">
              {user?.email}
            </span>
            <Button variant="ghost" size="icon" onClick={handleLogout} title="Logout" className="cursor-pointer">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-2xl px-4 py-6 space-y-4">
            <Stepper step={step} maxStep={maxStep} items={[
              { label: "Models", done: modelsDone },
              { label: "Chat", done: chatDone },
              { label: "Memory", done: memoryDone },
              { label: "Test", done: false },
            ]} onSelect={setStep} />

            {message && (
              <div
                className={`text-xs rounded-md px-3 py-2 border ${
                  message.kind === "ok"
                    ? "border-emerald-700/50 bg-emerald-950/30 text-emerald-300"
                    : "border-red-700/50 bg-red-950/30 text-red-300"
                }`}
              >
                {message.text}
              </div>
            )}

            {step === 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Models</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {config.triplets.length === 0 && (
                    <div className="border border-dashed rounded-md p-8 text-center space-y-3">
                      <p className="text-sm text-muted-foreground">
                        Add a model to get started.
                      </p>
                      <Button onClick={openAdd} className="cursor-pointer">
                        <Plus className="h-4 w-4" /> Add model
                      </Button>
                    </div>
                  )}
                  {config.triplets.map((t, i) => (
                    <TripletRow
                      key={i}
                      index={i}
                      triplet={t}
                      catalog={catalog}
                      status={tripletTests[t.alias]}
                      onEdit={() => openEdit(i)}
                      onRemove={() => removeTriplet(i)}
                    />
                  ))}
                  {config.triplets.length > 0 && (
                    <Button variant="outline" size="sm" onClick={openAdd} className="cursor-pointer">
                      <Plus className="h-4 w-4" /> Add model
                    </Button>
                  )}
                  {config.triplets.length > 0 && (
                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-t border-border pt-3">
                      <p className="text-xs text-muted-foreground">
                        Each model is tested automatically when added. Create more profiles (other providers or keys) or continue.
                      </p>
                      <Button onClick={() => setStep(1)} className="cursor-pointer shrink-0">
                        Continue to Chat <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {step === 1 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-1.5">
                    Chat
                    <Info tip="The model that answers students. Students attach homework photos, so pick an image-capable model." />
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <OrderEditor
                    order={config.chat.order}
                    aliases={aliases}
                    fallbackTip="If the primary fails (rate limit or server error), we try the next in order."
                    onAdd={(alias) => patchOperation("chat", { order: [...config.chat.order, alias] })}
                    onRemove={(alias) => patchOperation("chat", { order: config.chat.order.filter((a) => a !== alias) })}
                    onMove={(idx, dir) => moveInOrder("chat", idx, dir)}
                  />
                  <div className="flex justify-end">
                    <Button onClick={() => setStep(2)} disabled={!chatDone} className="cursor-pointer">
                      Continue to Memory <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {step === 2 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-1.5">
                    Memory
                    <Info tip="Runs in the background: names your chats and records what each student is working on. Use the cheapest model." />
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <OrderEditor
                    order={config.memory.order}
                    aliases={aliases}
                    fallbackTip="If the primary fails (rate limit or server error), we try the next in order."
                    onAdd={(alias) => patchOperation("memory", { order: [...config.memory.order, alias] })}
                    onRemove={(alias) => patchOperation("memory", { order: config.memory.order.filter((a) => a !== alias) })}
                    onMove={(idx, dir) => moveInOrder("memory", idx, dir)}
                  />
                  <div className="flex justify-end">
                    <Button onClick={() => setStep(3)} disabled={!memoryDone} className="cursor-pointer">
                      Continue to Test <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {step === 3 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Test</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <SummaryRow label="Chat" value={config.chat.order.join(" → ") || "—"} />
                  <SummaryRow label="Memory" value={config.memory.order.join(" → ") || "—"} />
                  <div className="flex items-center gap-2">
                    <Button onClick={handleTest} disabled={testing} className="cursor-pointer">
                      {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
                      Test
                    </Button>
                    <Button variant="outline" onClick={() => navigate("/chat")} className="cursor-pointer">
                      Back to chat
                    </Button>
                  </div>
                  {testResults && <TestResults results={testResults} />}
                </CardContent>
              </Card>
            )}

            <Accordion type="single" collapsible>
              <AccordionItem value="advanced">
                <AccordionTrigger className="text-sm text-muted-foreground">
                  Advanced
                </AccordionTrigger>
                <AccordionContent className="space-y-4">
                  <RoutingRules
                    title="Chat fallbacks"
                    config={config.chat}
                    aliases={aliases}
                    onToggleRule={(when, alias) => toggleRuleAlias("chat", when, alias)}
                  />
                  <RoutingRules
                    title="Memory fallbacks"
                    config={config.memory}
                    aliases={aliases}
                    onToggleRule={(when, alias) => toggleRuleAlias("memory", when, alias)}
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={handleExport} className="cursor-pointer">
                      <Download className="h-3.5 w-3.5" /> Export YAML
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => setImportOpen(true)} className="cursor-pointer">
                      <Upload className="h-3.5 w-3.5" /> Import YAML
                    </Button>
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{editingIndex === null ? "Add model" : "Edit model"}</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div className="space-y-1">
                <Label className="text-xs">Provider</Label>
                <Select value={form.provider} onValueChange={(v) => setForm({ ...form, provider: v, model: "" })}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {catalog.providers.map((p) => (
                      <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Model</Label>
                <ModelSelect provider={form.provider} model={form.model} catalog={catalog} onChange={(m) => setForm({ ...form, model: m })} />
                <ModelMeta model={catalog.models.find((m) => m.id === form.model && m.provider === form.provider)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs flex items-center gap-1">
                  Alias
                  <Info tip="A short name used to reference this model in the Chat and Memory steps." />
                </Label>
                <Input
                  value={form.alias}
                  placeholder="e.g. flash"
                  onChange={(e) => setForm({ ...form, alias: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs flex items-center gap-1">
                  API key
                  <Info tip="Encrypted at rest and decrypted only at the moment of a call." />
                </Label>
                <Input
                  type="password"
                  value={form.api_key}
                  placeholder={editingTriplet?.has_key ? "Leave blank to keep current" : "sk-…"}
                  onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                  autoComplete="off"
                />
                <KeyHelp providerId={form.provider} catalog={catalog} selectedModelId={form.model} />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)} className="cursor-pointer">
                Cancel
              </Button>
              <Button
                onClick={submitDialog}
                disabled={!form.model || !form.alias.trim() || (!editingTriplet?.has_key && !form.api_key && editingIndex === null)}
                className="cursor-pointer"
              >
                {editingIndex === null ? "Add" : "Save"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={importOpen} onOpenChange={setImportOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Import YAML</DialogTitle>
            </DialogHeader>
            <Textarea
              rows={10}
              placeholder="Paste a shared LLM config YAML…"
              value={importYaml}
              onChange={(e) => setImportYaml(e.target.value)}
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setImportOpen(false)} className="cursor-pointer">
                Cancel
              </Button>
              <Button onClick={handleImport} disabled={!importYaml.trim()} className="cursor-pointer">
                Import
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </TooltipProvider>
  );
}

// --- helpers ---

function replaceAlias(prev: LLMConfigUI, oldAlias: string, newAlias: string, triplets: TripletUI[]): LLMConfigUI {
  const rename = (list: string[]) => list.map((a) => (a === oldAlias ? newAlias : a));
  const renameRules = (rules: RuleUI[]) =>
    rules.map((r) => ({ ...r, use: r.use.map((a) => (a === oldAlias ? newAlias : a)) }));
  return {
    ...prev,
    triplets,
    chat: { ...prev.chat, order: rename(prev.chat.order), rules: renameRules(prev.chat.rules) },
    memory: { ...prev.memory, order: rename(prev.memory.order), rules: renameRules(prev.memory.rules) },
  };
}

function stripAlias(op: OperationConfigUI, alias: string): OperationConfigUI {
  return {
    order: op.order.filter((a) => a !== alias),
    rules: op.rules.map((r) => ({ ...r, use: r.use.filter((a) => a !== alias) })),
  };
}

// --- small pieces ---

function Info({ tip }: { tip: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-help text-muted-foreground">
          <InfoIcon className="h-3.5 w-3.5" />
        </span>
      </TooltipTrigger>
      <TooltipContent side="right">{tip}</TooltipContent>
    </Tooltip>
  );
}

function KeyHelp({
  providerId,
  catalog,
  selectedModelId,
}: {
  providerId: string;
  catalog: CatalogInfo;
  selectedModelId: string;
}) {
  const provider = catalog.providers.find((p) => p.id === providerId);
  if (!provider) return null;
  const model = catalog.models.find((m) => m.id === selectedModelId && m.provider === providerId);
  const isFree = model?.tier === "free";
  return (
    <div className="rounded-md border border-border/60 bg-muted/40 px-2.5 py-2 space-y-1.5 text-xs text-muted-foreground">
      <p>
        The key lets {provider.name} run the model on your behalf — it&apos;s how the app reaches it.
        <a
          href={provider.key_url}
          target="_blank"
          rel="noreferrer"
          className="text-primary hover:underline font-medium ml-1"
        >
          Get a key ↗
        </a>
      </p>
      <p>
        Pay-as-you-go, billed by {provider.name}: a typical homework answer costs a fraction of a cent
        {isFree ? " — this model is free" : " (priced per 1M tokens)"}.
      </p>
      <p>
        Keys are encrypted at rest, sent only to {provider.name} at request time, and can be revoked anytime.
      </p>
    </div>
  );
}

function SaveIndicator({ state }: { state: SaveState }) {
  if (state === "saving") {
    return (
      <span className="text-xs text-muted-foreground flex items-center gap-1">
        <Loader2 className="h-3 w-3 animate-spin" /> Saving…
      </span>
    );
  }
  if (state === "saved") {
    return (
      <span className="text-xs text-emerald-400 flex items-center gap-1">
        <Check className="h-3 w-3" /> Saved
      </span>
    );
  }
  if (state === "error") {
    return <span className="text-xs text-red-400">Save failed</span>;
  }
  return null;
}

function Stepper({
  step,
  maxStep,
  items,
  onSelect,
}: {
  step: number;
  maxStep: number;
  items: { label: string; done: boolean }[];
  onSelect: (i: number) => void;
}) {
  return (
    <div className="flex items-center gap-1 sm:gap-2">
      {items.map((item, i) => {
        const active = i === step;
        const locked = i > maxStep;
        return (
          <button
            key={item.label}
            onClick={() => !locked && onSelect(i)}
            disabled={locked}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors cursor-pointer ${
              active
                ? "border-primary/50 bg-primary/10 text-primary font-semibold"
                : locked
                  ? "border-border text-muted-foreground/50 cursor-not-allowed"
                  : "border-border text-muted-foreground hover:bg-accent"
            }`}
          >
            <span
              className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] ${
                item.done
                  ? "bg-emerald-500/20 text-emerald-300"
                  : active
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground"
              }`}
            >
              {item.done ? <Check className="h-3 w-3" /> : i + 1}
            </span>
            <span>{item.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function TripletRow({
  index,
  triplet,
  catalog,
  status,
  onEdit,
  onRemove,
}: {
  index: number;
  triplet: TripletUI;
  catalog: CatalogInfo;
  status?: TripletTestStatus;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const model = catalog.models.find((m) => m.id === triplet.model && m.provider === triplet.provider);
  const provider = catalog.providers.find((p) => p.id === triplet.provider);
  return (
    <div className="flex items-center gap-2 rounded-md border border-border px-3 py-2">
      <span className="text-xs text-muted-foreground tabular-nums w-5 shrink-0">{index + 1}</span>
      <Badge variant="secondary" className="font-mono shrink-0">{triplet.alias}</Badge>
      <span className="text-sm flex-1 truncate">{model?.label ?? triplet.model}</span>
      {model && (
        <span className="text-xs text-muted-foreground shrink-0 hidden sm:inline">
          {model.price_in}/{model.price_out}
        </span>
      )}
      {provider && (
        <span className="text-xs text-muted-foreground/70 shrink-0 hidden md:inline">{provider.name}</span>
      )}
      {status?.state === "testing" && (
        <span title="Testing…">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground shrink-0" />
        </span>
      )}
      {status?.state === "ok" && (
        <Badge variant="outline" className="border-emerald-700/40 text-emerald-300 shrink-0 gap-1">
          <Check className="h-3 w-3" /> {status.latencyMs != null ? `${status.latencyMs}ms` : "ok"}
        </Badge>
      )}
      {status?.state === "failed" && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="outline" className="border-red-700/40 text-red-300 shrink-0 cursor-help">
              failed
            </Badge>
          </TooltipTrigger>
          <TooltipContent>{status.error}</TooltipContent>
        </Tooltip>
      )}
      <Button variant="ghost" size="icon-sm" className="h-7 w-7 cursor-pointer shrink-0" onClick={onEdit} title="Edit">
        <Pencil className="h-3.5 w-3.5" />
      </Button>
      <Button variant="ghost" size="icon" className="h-7 w-7 cursor-pointer shrink-0" onClick={onRemove} title="Remove">
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

function ModelSelect({
  provider,
  model,
  catalog,
  onChange,
}: {
  provider: string;
  model: string;
  catalog: CatalogInfo;
  onChange: (modelId: string) => void;
}) {
  const options = catalog.models.filter((m) => m.provider === provider);
  const known = options.some((m) => m.id === model);
  return (
    <Select value={known ? model : ""} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue placeholder="Choose a model…" />
      </SelectTrigger>
      <SelectContent>
        {!known && model && (
          <SelectItem value={model}>{model} (custom)</SelectItem>
        )}
        {options.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            <span className="flex items-center gap-2">
              {m.label}
              <span className="text-xs text-muted-foreground">
                {m.price_in}/{m.price_out}
              </span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

const TIER_BADGE: Record<string, { label: string; className: string }> = {
  premium: { label: "Premium", className: "border-amber-500/40 text-amber-300" },
  standard: { label: "Standard", className: "border-blue-500/40 text-blue-300" },
  budget: { label: "Budget", className: "border-emerald-700/40 text-emerald-300" },
  free: { label: "Free", className: "border-sky-500/40 text-sky-300" },
};

function ModelMeta({ model }: { model: ModelInfo | undefined }) {
  if (!model) return null;
  const tier = TIER_BADGE[model.tier];
  return (
    <div className="flex flex-wrap items-center gap-1.5 pt-1">
      {tier && (
        <Badge variant="outline" className={tier.className}>{tier.label}</Badge>
      )}
      {model.supports_images && (
        <Badge variant="outline" className="gap-1">
          <ImageIcon className="h-3 w-3" /> Image
        </Badge>
      )}
      {model.recommended !== "either" && (
        <Badge variant="outline" className={`gap-1 ${model.recommended === "chat" ? "border-primary/40 text-primary" : "border-emerald-700/40 text-emerald-300"}`}>
          {model.recommended === "chat" ? <Sparkles className="h-3 w-3" /> : <Zap className="h-3 w-3" />}
          {model.recommended === "chat" ? "Best for chat" : "Best for memory"}
        </Badge>
      )}
      <span className="text-xs text-muted-foreground/80">
        {model.price_in} in / {model.price_out} out per 1M
      </span>
    </div>
  );
}

function OrderEditor({
  order,
  aliases,
  fallbackTip,
  onAdd,
  onRemove,
  onMove,
}: {
  order: string[];
  aliases: string[];
  fallbackTip: string;
  onAdd: (alias: string) => void;
  onRemove: (alias: string) => void;
  onMove: (idx: number, dir: -1 | 1) => void;
}) {
  const available = aliases.filter((a) => !order.includes(a));
  return (
    <div className="space-y-2">
      {order.length === 0 && (
        <p className="text-sm text-muted-foreground">Pick a model.</p>
      )}
      {order.map((alias, idx) => (
        <div key={alias} className="flex items-center gap-2 rounded-md border border-border px-3 py-2">
          <Badge variant={idx === 0 ? "default" : "outline"} className="w-16 justify-center shrink-0">
            {idx === 0 ? "Primary" : `#${idx + 1}`}
          </Badge>
          <span className="text-sm flex-1 truncate font-medium">{alias}</span>
          <Button variant="ghost" size="icon-sm" className="h-7 w-7 cursor-pointer shrink-0" disabled={idx === 0} onClick={() => onMove(idx, -1)} title="Move up">
            <ChevronUp className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" className="h-7 w-7 cursor-pointer shrink-0" disabled={idx === order.length - 1} onClick={() => onMove(idx, 1)} title="Move down">
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" className="h-7 w-7 cursor-pointer shrink-0" onClick={() => onRemove(alias)} title="Remove">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      {available.length > 0 && (
        <div className="flex items-center gap-2">
          <Select value="" onValueChange={onAdd}>
            <SelectTrigger className="flex-1">
              <SelectValue placeholder={order.length === 0 ? "Choose a model…" : "Add fallback…"} />
            </SelectTrigger>
            <SelectContent>
              {available.map((a) => (
                <SelectItem key={a} value={a}>{a}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Info tip={fallbackTip} />
        </div>
      )}
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium truncate">{value}</span>
    </div>
  );
}

function RoutingRules({
  title,
  config,
  aliases,
  onToggleRule,
}: {
  title: string;
  config: OperationConfigUI;
  aliases: string[];
  onToggleRule: (when: "rate_limit" | "server_error", alias: string) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      {ROUTING_REASONS.map((reason) => {
        const rule = config.rules.find((r) => r.when === reason.value);
        const selected = rule?.use ?? [];
        return (
          <div key={reason.value} className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground w-14 shrink-0 flex items-center gap-1">
              {reason.label}
              <Info tip={reason.tip} />
            </span>
            {aliases.length === 0 ? (
              <span className="text-xs text-muted-foreground/60">Add models first.</span>
            ) : (
              aliases.map((a) => (
                <Badge
                  key={a}
                  variant={selected.includes(a) ? "default" : "outline"}
                  className="cursor-pointer"
                  onClick={() => onToggleRule(reason.value, a)}
                >
                  {a}
                </Badge>
              ))
            )}
          </div>
        );
      })}
      <p className="text-xs text-muted-foreground/60">
        Empty = move to the next in order.
      </p>
    </div>
  );
}

function TestResults({ results }: { results: PingResult[] }) {
  return (
    <div className="space-y-2 pt-1">
      {results.map((r) => (
        <div key={r.alias} className="flex items-center gap-2 text-sm rounded-md border border-border px-3 py-2">
          <Badge variant={r.ok ? "default" : "destructive"} className="shrink-0">
            {r.ok ? "OK" : "FAIL"}
          </Badge>
          <span className="font-medium shrink-0">{r.alias}</span>
          <span className="text-xs text-muted-foreground truncate">— {r.provider} / {r.model}</span>
          <span className="text-xs text-muted-foreground ml-auto shrink-0">
            {r.ok ? `${r.latency_ms}ms` : r.error}
          </span>
        </div>
      ))}
    </div>
  );
}
