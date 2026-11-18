import { afterEach, describe, expect, it, vi } from "vitest";
import { SseDecoder } from "./sse";
import { streamChat } from "./api";
import type { StreamEvent } from "../types";

describe("SseDecoder", () => {
  it("reassembles split UTF-8 and frame boundaries", () => {
    const decoder = new SseDecoder();
    const bytes = new TextEncoder().encode('data: {"event":"token","text":"你好"}\n\ndata: {"event":"done","trace_id":"t"}\n\n');
    const cut = bytes.indexOf(0xe5) + 1;
    expect(decoder.feed(bytes.slice(0, cut))).toEqual([]);
    expect(decoder.feed(bytes.slice(cut, bytes.length - 1))).toEqual([
      { event: "token", text: "你好" },
    ]);
    expect(decoder.feed(bytes.slice(bytes.length - 1))).toEqual([
      { event: "done", trace_id: "t" },
    ]);
  });

  it("handles CRLF, comments and an unterminated final frame", () => {
    const decoder = new SseDecoder();
    expect(decoder.feed(new TextEncoder().encode(': ping\r\ndata: {"event":"started","trace_id":"x"}\r\n\r\n'))).toEqual([
      { event: "started", trace_id: "x" },
    ]);
    decoder.feed(new TextEncoder().encode('data: {"event":"done","trace_id":"x"}'));
    expect(decoder.finish()).toEqual([{ event: "done", trace_id: "x" }]);
  });

  it("rejects a stream that closes before its final answer event", async () => {
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async () => new Response('data: {"event":"token","text":"draft"}\n\n', {
        headers: { "Content-Type": "text/event-stream" },
      });
      await expect(streamChat({ message: "q", user_id: "u" }, () => {}, new AbortController().signal)).rejects.toThrow("未收到最终回答");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe("streamChat terminal-event observation", () => {
  afterEach(() => vi.unstubAllGlobals());

  it.each(["answered", "execution_failed", "insufficient_evidence", "evidence_only"] as const)(
    "captures immediate %s answer and done events from one response",
    async (status) => {
      const responseData = {
        answer: status === "answered" ? "Verified answer" : "Status message",
        session_id: "session-1",
        trace_id: "trace-1",
        status,
        generation_backend: "deepseek",
        retrieval_backend: "bm25",
        applied_filters: null,
        corpus_identity: null,
        citations: [],
        error_code: null,
        token_usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2, usage_known: true },
        latency: { total_ms: 12, llm_ms: 8 },
      };
      const frames = [
        `data: ${JSON.stringify({ event: "answer", data: responseData })}\n\n`,
        `data: ${JSON.stringify({ event: "done", trace_id: "trace-1" })}\n\n`,
      ].join("");
      vi.stubGlobal("fetch", vi.fn(async () => new Response(frames, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      })));

      const events: StreamEvent[] = [];
      await streamChat({ message: "q", user_id: "u" }, (event) => events.push(event), new AbortController().signal);

      expect(events.map((event) => event.event)).toEqual(["answer", "done"]);
      expect((events[0]?.event === "answer" ? events[0].data.status : undefined)).toBe(status);
    },
  );

  it("captures HTTP 200 execution_failed as a terminal business result", async () => {
    const responseData = {
      answer: "服务暂时不可用。", session_id: "s", trace_id: "t", status: "execution_failed",
      generation_backend: "deepseek", retrieval_backend: "bm25", applied_filters: null,
      corpus_identity: null, citations: [], error_code: "provider_unavailable",
      token_usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, usage_known: false },
      latency: { total_ms: 5, llm_ms: 4 },
    };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(
      `data: ${JSON.stringify({ event: "answer", data: responseData })}\n\n`,
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    )));
    const events: StreamEvent[] = [];
    await streamChat({ message: "q", user_id: "u" }, (event) => events.push(event), new AbortController().signal);
    expect(events).toHaveLength(1);
    expect((events[0]?.event === "answer" ? events[0].data.status : undefined)).toBe("execution_failed");
  });
});
