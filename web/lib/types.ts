// Shapes of docs/workbench-api.md (the backend contract) plus pure helpers. No data lives here.

export type Kind = "doc" | "issue" | "discussion" | "pr" | "commit";
export type Status = "supported" | "inferred" | "unknown";

export interface Node {
  id: string;
  cid: string; // canonical id as stored in Neo4j (== id)
  kind: Kind;
  source: "jira" | "github" | "slack" | "confluence";
  ref: string; // short human label
  title: string;
  text: string;
  author: string;
  time: string;
  url: string;
  paths?: string[];
  scope: string; // "owner/repo" | Jira project key | Slack channel id
}

export interface Edge {
  from: string;
  to: string;
  // INFERRED is kept for forward compatibility; the backend graph holds only explicit links today.
  rel: "CONTAINS" | "REFERENCES" | "REPLIES_TO" | "PARENT_OF" | "CHANGES" | "INFERRED";
  origin: "structural" | "text";
  locator: string;
  why?: string; // only for inferred edges
}

export interface Graph { nodes: Node[]; edges: Edge[] }

export interface Cite {
  node: string;
  quote?: string;
}
export interface Claim {
  id: string;
  text: string;
  status: Status;
  note?: string;
  cites: Cite[];
  afterStep: number; // revealed once the trace reaches this step
}
export interface Step {
  kind: "understand" | "plan" | "tool" | "gap" | "synthesize";
  label: string;
  detail: string;
  ms: number;
}
export interface Check {
  label: string;
  state: "holds" | "changed" | "unknown";
  detail: string;
}
export interface Investigation {
  id: string;
  question: string;
  mode: "why" | "debug" | "change";
  file?: string;
  line?: number;
  summary: string;
  nodes: string[];
  claims: Claim[];
  gaps: string[];
  trace: Step[];
  checks: Check[];
  excluded: { node: string; reason: string }[];
  confidence: "high" | "medium" | "low";
  provider: string;
  model: string;
  prompt_version: string;
  created_at: string;
}
export interface InvestigationRow {
  id: string;
  question: string;
  file?: string | null;
  line?: number | null;
  confidence: string;
  created_at: string;
}
export interface CodeLine {
  text: string;
  blame: string | null; // node id of the commit, null when unknown
}
export interface CodeFile {
  path: string;
  lines: CodeLine[];
  complete: boolean;
  note?: string;
}

export interface Connected { repos: string[]; jira: string[]; slack: string[]; docs?: string[] }
export interface Provider { name: string; model: string; configured: boolean }

/** Write-only secret state: values of secret keys are never returned, only a masked hint. */
export interface SecretState { set: boolean; source: "workspace" | "env" | null; value?: string; hint?: string }
export type Secrets = Record<string, SecretState>;
export type IntegrationId = "github" | "jira" | "slack" | "llm";
export interface IntegrationStatus { configured: boolean; secrets: Secrets; targets?: number }

/** Connected targets of a workspace (PUT /api/w/{ws}/workspace). github.repos are bare names under one owner. */
export interface Targets {
  name?: string;
  github: { owner: string; repos: string[] };
  jira: { site: string; projects: string[] };
  slack: { workspace: string; channels: string[] };
}

/** PUT /workspace merges per section: send only what changes. */
export interface TargetsPatch {
  name?: string;
  github?: Partial<Targets["github"]>;
  jira?: Partial<Targets["jira"]>;
  slack?: Partial<Targets["slack"]>;
}

export interface WorkbenchInfo {
  // `targets` is optional: when the server includes the clean workspace here the UI prefills Jira site / Slack subdomain.
  workspace: { slug: string; name: string; demo: boolean; targets?: Targets };
  connected: Connected;
  catalog: Connected;
  indexed_repos: string[];
  neo4j: { ok: boolean; counts?: Record<string, number> };
  integrations: Record<IntegrationId, IntegrationStatus>;
  providers: Provider[];
  names?: { channels: Record<string, string>; users: Record<string, string> };
  model?: { provider: string; model: string; source: "workspace" | "user" | "server" };
}

export interface WorkspaceRow {
  slug: string;
  name: string;
  demo: boolean;
  connected: { repos: number; jira: number; slack: number; docs?: number };
  last_sync?: { state: string; finished_at?: string | null } | null;
  owned?: boolean; // the caller owns it
  shared?: boolean; // visible to everyone, read-only (shared demo)
}

export type StreamStatus = "running" | "done" | "incomplete" | "failed";
export interface SyncStream {
  stream: string;
  status: StreamStatus;
  pages: number;
  fetched: number;
  persisted: number;
  errors: { stage: string; type: string; message: string }[];
}
export type SyncMode = "standard" | "deep";
export interface SyncStatus {
  state: "idle" | "running" | "done" | "failed";
  mode: SyncMode;
  started_at?: string | null;
  finished_at?: string | null;
  streams: SyncStream[];
  totals: { fetched: number; persisted: number; errors: number };
  graph?: { artifacts: number; edges: number; stubs: number } | null;
  complete: boolean;
  error?: string | null;
  id?: string;
  log?: LogLine[];
}

export interface Resource { id: string; name: string; private?: boolean; detail?: string }
export interface TestResult { ok: boolean; detail: string; account?: string }

export const KINDS: { kind: Kind; label: string; color: string }[] = [
  { kind: "doc", label: "Doc", color: "#34d399" },
  { kind: "issue", label: "Issue", color: "#fb923c" },
  { kind: "discussion", label: "Discussion", color: "#f472b6" },
  { kind: "pr", label: "Pull request", color: "#a78bfa" },
  { kind: "commit", label: "Commit", color: "#60a5fa" },
];
export const KIND_COLOR = Object.fromEntries(KINDS.map((k) => [k.kind, k.color])) as Record<Kind, string>;

export const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
export const fmtTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });

// ---- accounts, user models, runs, ingestion (docs/accounts-and-settings-api.md)
export interface Me {
  auth: "enabled" | "disabled";
  methods?: ("github" | "password")[];
  callback_url?: string; // the GitHub OAuth callback URL this server uses (must match the OAuth app exactly)
  user: { id: string; login: string; name: string; avatar_url: string } | null;
}
export interface ModelField { key: string; label: string; secret: boolean; set: boolean; hint?: string; value?: string }
export interface ModelProvider {
  name: string; label: string; model: string; configured: boolean;
  source: "user" | "server" | null; editable: boolean; fields: ModelField[];
}
export interface UserModels {
  providers: ModelProvider[];
  default: { provider: string; model: string; source: "user" | "server" };
  selected: { provider: string; model: string };
}
export interface LogLine { ts: string; level: "info" | "warn" | "error"; stream?: string; message: string }
export interface RunMeta {
  id: string; state: "running" | "done" | "failed"; mode: SyncMode; started_at: string; finished_at?: string;
  complete: boolean; totals: { fetched: number; persisted: number; errors: number }; triggered_by?: string;
}
export interface Run extends RunMeta {
  streams: SyncStream[]; graph?: { artifacts: number; edges: number; stubs: number } | null; error?: string; log: LogLine[];
}
export interface Ingestion {
  neo4j: { ok: boolean };
  graph: { artifacts: number; edges: number; stubs: number } | null;
  by_source: { source: string; kind: string; count: number }[];
  repos: { repo: string; indexed: boolean }[];
  last_run: RunMeta | null;
  stages: { key: "fetched" | "stored" | "linked" | "indexed"; label: string; count: number; status: "ok" | "warn" | "idle" }[];
  plan: IngestPlan;
  timeline: { source: string; kind: string; oldest: string; newest: string; count: number }[];
  last_streams: { stream: string; status: StreamStatus; pages: number; fetched: number; persisted: number; errors: number }[];
}
export interface IngestPlan {
  pages: { standard: number; deep: number };
  order: string; incremental: boolean; idempotent: boolean; notes: string[];
  sources: { source: "github" | "jira" | "slack"; target: string; streams: {
    stream: string; label: string; order: string; page: number | null; includes: string;
    max: { standard: number | null; deep: number | null } }[] }[];
}
export const fmtStamp = (iso?: string | null) => (iso ? `${fmtDate(iso)} ${fmtTime(iso)} UTC` : "");

// Memory (docs/memory.md): ADRs, rules and episodes proposed from evidence and approved by a person.
export type MemoryKind = "adr" | "rule" | "episode";
export type MemoryStatus = "draft" | "staged" | "approved" | "rejected" | "retired";
export interface MemoryEvidence { id: string; kind: string; title: string | null; quote: string; url: string | null; time: string | null }
export interface MemoryEntry {
  id: string; kind: MemoryKind; status: MemoryStatus; title: string; body: string; evidence: MemoryEvidence[]; anchor: string;
  triage: string; version: number; reason?: string | null; created_at: string; updated_at: string;
  served: { version: number; title: string; body: string; approved_by: string; approved_at: string } | null;
  revisions: { version: number; at: string; by: string; note: string }[];
}
export interface MemoryList { counts: Record<MemoryStatus, number>; items: MemoryEntry[] }
export interface TriageResult { action: "created" | "refined" | "unchanged" | "suppressed" | "nothing"; entry: MemoryEntry | null; note: string }
