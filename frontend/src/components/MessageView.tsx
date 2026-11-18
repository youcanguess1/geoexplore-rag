import { useEffect, useRef, useState } from "react";
import { Check, Copy, FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { formatFilters } from "../lib/filters";
import type { ChatStatus, Citation, Conversation, Message } from "../types";
import { Logo } from "./Logo";

const STATUS_LABELS: Record<ChatStatus, string> = {
  answered: "已回答",
  evidence_only: "仅提供原文证据，未进行模型生成",
  insufficient_evidence: "当前资料范围证据不足",
  execution_failed: "执行失败",
};

function CitationList({ citations }: { citations: Citation[] }) {
  const unique = citations.filter((item, index, all) => all.findIndex((other) => other.chunk_id === item.chunk_id) === index);
  if (!unique.length) return null;
  return <section className="citation-list" aria-label="回答引用">
    <span className="citation-heading">原文证据</span>
    {unique.map((item) => <article className="citation-card" key={item.chunk_id}>
      <div className="citation-title"><FileText size={15} /><strong>{item.title || item.source_file || "未提供文档标题"}</strong></div>
      <dl>
        <div><dt>PDF 物理页</dt><dd>{item.page_number === null ? "未提供" : `第 ${item.page_number} 页`}</dd></div>
        <div><dt>Chunk</dt><dd><code>{item.chunk_id}</code></dd></div>
        <div><dt>原文摘录</dt><dd className="citation-excerpt">{item.excerpt || "未提供"}</dd></div>
      </dl>
      <details>
        <summary>审计元数据</summary>
        <dl className="citation-metadata">
          <div><dt>document_id</dt><dd><code>{item.document_id || "未提供"}</code></dd></div>
          <div><dt>分类</dt><dd>{item.data_type || "未提供"}</dd></div>
          <div><dt>文档类型</dt><dd>{item.document_type || "未提供"}</dd></div>
          <div><dt>语言</dt><dd>{item.language || "未提供"}</dd></div>
          <div><dt>document_sha256</dt><dd><code>{item.document_sha256 || "未提供"}</code></dd></div>
          <div><dt>corpus_fingerprint</dt><dd><code>{item.corpus_fingerprint || "未提供"}</code></dd></div>
        </dl>
      </details>
    </article>)}
  </section>;
}

function StatusBlock({ message }: { message: Message }) {
  if (message.state === "streaming") return <p className="message-note">正在接收未验证草稿，等待最终校验结果。</p>;
  if (message.state === "stopped") return <p className="message-note">生成已停止，未收到最终校验结果。下方内容不是正式答案或引用依据。</p>;
  if (message.state === "error") return <div className="stream-interrupted" role="alert">
    <strong>请求未完成</strong>
    <p>{message.failureMessage || "连接在最终回答前中断。"}</p>
    {message.content && <p>下方仅保留未完成草稿，未通过最终校验，不应作为正式答案或引用依据。</p>}
  </div>;
  if (!message.status) return null;
  return <div className={`status-note status-${message.status}`}><strong>{STATUS_LABELS[message.status]}</strong>{message.appliedFilters !== undefined && <span>实际范围：{formatFilters(message.appliedFilters)}</span>}</div>;
}

interface MessageViewProps { conversation: Conversation; busy: boolean; }

export function MessageView({ conversation, busy }: MessageViewProps) {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [conversation.messages]);

  async function copy(message: Message) {
    try { await navigator.clipboard.writeText(message.content); setCopiedId(message.id); window.setTimeout(() => setCopiedId(null), 1800); } catch { /* Clipboard can be unavailable. */ }
  }

  return <div className="message-list" aria-label="对话内容">
    {conversation.messages.map((message) => message.role === "user"
      ? <div className="message user-message" key={message.id}><div className="user-bubble">{message.content}</div></div>
      : <div className="message assistant-message" key={message.id}>
          <div className="assistant-avatar"><Logo small /></div>
          <div className="assistant-body">
            <StatusBlock message={message} />
            {message.content ? message.state !== "complete" && !message.status
              ? <pre className="unverified-draft">{message.content}</pre>
              : <div className={`markdown ${message.status === "execution_failed" ? "message-error" : ""}`}><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div>
              : <div className="thinking"><span /><span /><span /></div>}
            {message.state === "complete" && <>
              <CitationList citations={message.citations ?? []} />
              <div className="message-tools"><button disabled={busy} aria-label="复制回答" title="复制回答" onClick={() => void copy(message)}>{copiedId === message.id ? <Check size={16} /> : <Copy size={16} />}</button></div>
            </>}
          </div>
        </div>)}
    <div ref={endRef} />
  </div>;
}
