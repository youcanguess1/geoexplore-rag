export type ChatStatus = "answered" | "evidence_only" | "insufficient_evidence" | "execution_failed";

export interface RetrievalFilters {
  document_ids: string[];
  data_types: ("01_Documents" | "02_Academic")[];
  document_types: ("report" | "standard" | "textbook" | "paper" | "review" | "technical_report")[];
  languages: string[];
}

export interface Citation {
  document_id: string;
  title: string;
  chunk_id: string;
  section: string | null;
  source_file: string;
  page_number: number | null;
  excerpt: string;
  data_type: string;
  document_type: string;
  language: string;
  document_sha256: string;
  corpus_fingerprint: string;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  usage_known: boolean;
}

export interface CorpusIdentity {
  corpus_id: string;
  corpus_fingerprint: string;
  parser_backend: string;
  parser_version: string;
  chunking_version: string;
  document_count: number;
  chunk_count: number;
}

export interface ChatResponse {
  answer: string;
  session_id: string;
  trace_id: string;
  status: ChatStatus;
  generation_backend: string;
  retrieval_backend: string;
  applied_filters: RetrievalFilters | null;
  corpus_identity: CorpusIdentity | null;
  citations: Citation[];
  error_code: string | null;
  token_usage: TokenUsage;
  latency: { total_ms: number; llm_ms: number };
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  user_id: string;
  filters?: RetrievalFilters;
}

export type StreamEvent =
  | { event: "started"; trace_id: string }
  | { event: "node"; node: string }
  | { event: "token"; text: string }
  | { event: "answer"; data: ChatResponse }
  | { event: "done"; trace_id: string };

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  state: "complete" | "streaming" | "error" | "stopped";
  citations?: Citation[];
  traceId?: string;
  latencyMs?: number;
  status?: ChatStatus;
  appliedFilters?: RetrievalFilters | null;
  corpusIdentity?: CorpusIdentity | null;
  generationBackend?: string;
  retrievalBackend?: string;
  tokenUsage?: TokenUsage;
  errorCode?: string | null;
  failureMessage?: string;
}

export interface Conversation {
  id: string;
  title: string;
  updatedAt: number;
  sessionId?: string;
  messages: Message[];
}
