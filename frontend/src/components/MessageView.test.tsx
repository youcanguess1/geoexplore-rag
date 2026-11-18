import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MessageView } from "./MessageView";
import type { Conversation } from "../types";

describe("answer presentation", () => {
  it("shows returned citation metadata and the applied service filter", () => {
    const conversation: Conversation = {
      id: "chat-1", title: "question", updatedAt: 0, messages: [{
        id: "answer-1", role: "assistant", state: "complete", content: "The evidence supports this.", status: "answered",
        appliedFilters: { document_ids: ["geo-a"], data_types: [], document_types: ["report"], languages: ["en"] },
        citations: [{ document_id: "geo-a", title: "Field Report", chunk_id: "geo-a_7", section: null, source_file: "field.pdf", page_number: 14, excerpt: "Original evidence excerpt.", data_type: "01_Documents", document_type: "report", language: "en", document_sha256: "a".repeat(64), corpus_fingerprint: "b".repeat(64) }],
      }],
    };
    const html = renderToStaticMarkup(<MessageView conversation={conversation} busy={false} />);
    expect(html).toContain("已回答");
    expect(html).toContain("PDF 物理页");
    expect(html).toContain("第 14 页");
    expect(html).toContain("Original evidence excerpt.");
    expect(html).toContain("类型：report");
  });

  it("labels partial token text as an unverified incomplete draft", () => {
    const conversation: Conversation = { id: "chat-2", title: "question", updatedAt: 0, messages: [{ id: "answer-2", role: "assistant", state: "error", content: "partial text", failureMessage: "连接已中断" }] };
    const html = renderToStaticMarkup(<MessageView conversation={conversation} busy={false} />);
    expect(html).toContain("请求未完成");
    expect(html).toContain("未通过最终校验");
    expect(html).toContain("partial text");
  });

  it("keeps a restored stopped stream out of normal final-answer rendering", () => {
    const conversation: Conversation = { id: "chat-4", title: "question", updatedAt: 0, messages: [{ id: "answer-4", role: "assistant", state: "stopped", content: "partial text" }] };
    const html = renderToStaticMarkup(<MessageView conversation={conversation} busy={false} />);
    expect(html).toContain("未收到最终校验结果");
    expect(html).toContain("unverified-draft");
  });
  it("does not present an execution failure as an answered response", () => {
    const conversation: Conversation = { id: "chat-3", title: "question", updatedAt: 0, messages: [{
      id: "answer-3", role: "assistant", state: "complete", content: "服务暂时不可用。", status: "execution_failed", citations: [],
      appliedFilters: { document_ids: [], data_types: [], document_types: ["report"], languages: [] },
    }] };
    const html = renderToStaticMarkup(<MessageView conversation={conversation} busy={false} />);
    expect(html).toContain("执行失败");
    expect(html).not.toContain("已回答");
    expect(html).toContain("类型：report");
  });
});
