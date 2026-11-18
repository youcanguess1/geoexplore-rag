import { afterEach, describe, expect, it } from "vitest";
import { loadConversations } from "./storage";

const KEY = "geoexplore-web:v2";
const savedLocalStorage = globalThis.localStorage;

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

afterEach(() => {
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: savedLocalStorage });
});

describe("conversation storage", () => {
  it("keeps the service-returned status, filters, and citations after reload", () => {
    const storage = new MemoryStorage();
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: storage });
    storage.setItem(KEY, JSON.stringify([{
      id: "conversation-1", title: "question", updatedAt: 1, messages: [{
        id: "answer-1", role: "assistant", content: "Evidence", state: "complete", status: "evidence_only",
        appliedFilters: { document_ids: ["geo-fs11503"], data_types: [], document_types: ["report"], languages: ["en"] },
        citations: [{ document_id: "geo-fs11503", title: "Study", chunk_id: "geo-fs11503_10", section: null, source_file: "fs11503.pdf", page_number: 2, excerpt: "Source text", data_type: "01_Documents", document_type: "report", language: "en", document_sha256: "a", corpus_fingerprint: "b" }],
      }],
    }]));

    const conversation = loadConversations()[0];
    expect(conversation).toBeDefined();
    const answer = conversation?.messages[0];
    expect(answer).toBeDefined();
    expect(answer).toMatchObject({
      status: "evidence_only",
      appliedFilters: { document_ids: ["geo-fs11503"], data_types: [], document_types: ["report"], languages: ["en"] },
    });
    expect(answer!.citations?.[0]).toMatchObject({ chunk_id: "geo-fs11503_10", page_number: 2 });
  });

  it("marks a persisted streaming response as stopped without treating it as final", () => {
    const storage = new MemoryStorage();
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: storage });
    storage.setItem(KEY, JSON.stringify([{ id: "conversation-2", title: "question", updatedAt: 1, messages: [{ id: "answer-2", role: "assistant", content: "draft", state: "streaming" }] }]));

    const conversation = loadConversations()[0];
    expect(conversation).toBeDefined();
    expect(conversation!.messages[0]).toMatchObject({
      state: "stopped",
      failureMessage: "页面刷新前未收到最终校验结果。",
    });
  });
});
