import { useEffect, useRef, useState } from "react";
import { ArrowDown, Menu, PanelLeftOpen } from "lucide-react";
import { checkHealth } from "./lib/api";
import { EMPTY_FILTERS, filtersForRequest } from "./lib/filters";
import { useChat } from "./hooks/useChat";
import { Composer } from "./components/Composer";
import { Logo } from "./components/Logo";
import { MessageView } from "./components/MessageView";
import { RetrievalFiltersPanel } from "./components/RetrievalFilters";
import { SearchDialog } from "./components/SearchDialog";
import { Sidebar } from "./components/Sidebar";
import type { RetrievalFilters } from "./types";

const SUGGESTIONS = [
  { title: "Canal study", prompt: "In the Nebraska canal study, when did diversions typically occur, and when were empty canals intermittently repaired?" },
  { title: "Rippable material", prompt: "At the Presidio of Monterey site, how deep did rippable material extend beneath Line A and Line B?" },
  { title: "SH-wave limits", prompt: "Why can SH-wave refraction fail to reveal a lower-velocity layer, and what thickness-related limitation also applies?" },
  { title: "Dipping boundary", prompt: "What field setup is required to analyze a dipping seismic-refraction boundary for a single array?" },
  { title: "Filtered evidence", prompt: "What is the title of the 2021 paper about shear-wave reflection and refraction methods?" },
  { title: "Evidence boundary", prompt: "What exact annual maintenance budget did the controlled seismic surveys require?" },
];

function App() {
  const chat = useChat();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [filters, setFilters] = useState<RetrievalFilters>({ ...EMPTY_FILTERS });
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">(() => localStorage.getItem("geoexplore-theme") === "dark" ? "dark" : "light");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("geoexplore-theme", theme); }, [theme]);
  useEffect(() => { const controller = new AbortController(); void checkHealth(controller.signal).then(setHealthy); return () => controller.abort(); }, []);
  useEffect(() => {
    function onKey(event: globalThis.KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setSearchOpen(true); }
      if (event.key === "Escape") { setSearchOpen(false); setSidebarOpen(false); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function newChat() { chat.select(null); setDraft(""); setFilters({ ...EMPTY_FILTERS }); setSidebarOpen(false); window.setTimeout(() => inputRef.current?.focus(), 0); }
  function selectChat(id: string) { chat.select(id); setSidebarOpen(false); setSearchOpen(false); }
  function suggest(prompt: string) { setDraft(prompt); inputRef.current?.focus(); }
  function send(message: string) { void chat.send(message, filtersForRequest(filters)); }

  return <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
    <Sidebar conversations={chat.conversations} activeId={chat.active?.id ?? null} open={sidebarOpen} onClose={() => { setSidebarOpen(false); setSidebarCollapsed(true); }} onNew={newChat} onSelect={selectChat} onRemove={chat.remove} onSearch={() => setSearchOpen(true)} onTheme={() => setTheme(theme === "light" ? "dark" : "light")} theme={theme} />
    <main className="main-panel">
      <header className="topbar">
        <button className="icon-button open-sidebar" aria-label="打开侧栏" title="打开侧栏" onClick={() => { setSidebarCollapsed(false); setSidebarOpen(true); }}>{sidebarCollapsed ? <PanelLeftOpen size={20} /> : <Menu size={20} />}</button>
        <span className="model-title">GeoExplore</span>
        <div className="topbar-right"><span className={`connection-pill ${healthy === false ? "offline" : ""}`}><span />{healthy === null ? "服务检查中" : healthy ? "服务可访问" : "服务未连接"}</span></div>
      </header>
      {chat.active ? <div className="chat-content"><MessageView conversation={chat.active} busy={chat.busy} /></div>
        : <div className="welcome"><div className="welcome-inner"><Logo /><h1>地质勘探技术资料检索问答</h1><p>仅基于当前已登记资料；当前已验证英文查询；回答会显示原文证据和 PDF 物理页码。</p><div className="suggestions">{SUGGESTIONS.map((item) => <button key={item.title} onClick={() => suggest(item.prompt)}><span className="suggestion-icon">⌁</span><span><strong>{item.title}</strong><small>{item.prompt}</small></span><ArrowDown size={15} /></button>)}</div></div></div>}
      <div className="retrieval-controls"><RetrievalFiltersPanel value={filters} disabled={chat.busy} onChange={setFilters} /></div>
      <Composer busy={chat.busy} onSend={send} onStop={chat.stop} draft={draft} onDraft={setDraft} inputRef={inputRef} />
    </main>
    {searchOpen && <SearchDialog conversations={chat.conversations} onClose={() => setSearchOpen(false)} onSelect={selectChat} />}
  </div>;
}

export default App;
