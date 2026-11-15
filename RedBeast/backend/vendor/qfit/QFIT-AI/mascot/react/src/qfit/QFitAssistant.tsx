/* Q-FIT assistant: the robin mascot in a screen corner; clicking it, the robin pulls the chat panel
   open with its beak. Copy the whole mascot/react/src/qfit folder into the app.
   Behaviour: docs/MASCOT_AND_CHAT_UI.md. */
import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { askQFit, type ChatContext, type ChatTurn, type QFitAction, type QFitResponse } from "./api";
import robinIcon from "./assets/robin-64.png";
import "./qfit-assistant.css";

export type Corner = "bottom-right" | "bottom-left" | "top-right" | "top-left";
export type MascotState = "idle" | "thinking" | "speaking" | "found" | "quiet";

export interface QFitAssistantProps {
  corner?: Corner;
  lang?: "tr" | "en";
  /** What the 3D view shows now; sent with every question. */
  context?: Omit<ChatContext, "locale">;
  /** Called with the UI actions of each answer (focus_map, display_image, ...). */
  onActions?: (actions: QFitAction[], response: QFitResponse) => void;
  /** Called with every answer (for data panels such as QFitDataPanel). */
  onResponse?: (response: QFitResponse) => void;
  /** Force a mascot state (for previews); undefined = automatic. */
  forceState?: MascotState;
}

const TEXT = {
  tr: { open: "Q-FIT asistanını aç", close: "Kapat", sub: "SPHEREx araştırma asistanı",
        placeholder: "Bir soru sor... (ör. Andromeda'yı göster)", send: "Gönder",
        hello: "Merhaba, ben Q-FIT. SPHEREx verisini bulmana ve neyin söylenip neyin söylenemeyeceğini anlamana yardım ederim.",
        caveats: "Belirsizlikler", sources: "Kaynaklar", ai: "Yapay zekâ açıklaması",
        fallback: "Yapay zekâ şu an kullanılamıyor; yanıt bilgi tabanından alındı.",
        network: "Sunucuya ulaşılamadı. Bağlantıyı kontrol edip tekrar dene." },
  en: { open: "Open the Q-FIT assistant", close: "Close", sub: "SPHEREx research assistant",
        placeholder: "Ask something... (e.g. show me Andromeda)", send: "Send",
        hello: "Hi, I am Q-FIT. I help you find SPHEREx data and understand what it can and cannot tell you.",
        caveats: "Caveats", sources: "Sources", ai: "AI explanation",
        fallback: "The AI is unavailable right now; this answer comes from the knowledge base.",
        network: "The server could not be reached. Check the connection and try again." },
};
const FOUND_MS = 1200, QUIET_MS = 2500, CHAR_MS = 18, MAX_SPEAK_MS = 4000;
const MOVE_MS = 180 + 600;   // grab + pull, as --qf-grab-ms + --qf-pull-ms in qfit-assistant.css

interface Message { id: number; who: "user" | "bot"; text: string; response?: QFitResponse }

/** Final mascot state after an answer has been shown. */
export function settleState(r: QFitResponse): { state: MascotState; holdMs?: number } {
  const d = r.data ?? ({} as QFitResponse["data"]);
  if (!r.success || d.fallback?.active || d.spherex_available === false || (d.tool_errors ?? []).length
      || r.intent === "error") return { state: "quiet", holdMs: QUIET_MS };
  if (d.spherex_available === true || (r.media ?? []).length) return { state: "found", holdMs: FOUND_MS };
  return { state: "idle" };
}

/** Escape everything, then allow **bold** only. */
function Rich({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return <>{parts.map((p, i) => p.startsWith("**") && p.endsWith("**") && p.length > 4
    ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>)}</>;
}

export function QFitAssistant({ corner = "bottom-right", lang, context = {}, onActions, onResponse, forceState }: QFitAssistantProps) {
  const language = lang ?? (navigator.language.startsWith("tr") ? "tr" : "en");
  const t = TEXT[language];
  const [open, setOpenState] = useState(false);
  const [motion, setMotion] = useState<"opening" | "closing" | null>(null);
  const [state, setState] = useState<MascotState>("idle");
  const [attention, setAttention] = useState(false);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([{ id: 0, who: "bot", text: t.hello }]);
  const history = useRef<ChatTurn[]>([]);
  const holdTimer = useRef<number>();
  const openRef = useRef(open);
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const motionTimer = useRef<number>();
  openRef.current = open;

  /** The robin pulls the panel open with its beak (or pushes it shut); CSS does the motion. */
  const setOpen = useCallback((next: boolean | ((o: boolean) => boolean)) => {
    const value = typeof next === "function" ? next(openRef.current) : next;
    if (value === openRef.current) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.clearTimeout(motionTimer.current);
    setMotion(reduced ? null : value ? "opening" : "closing");
    setOpenState(value);
    motionTimer.current = window.setTimeout(() => {
      setMotion(null);
      if (value) inputRef.current?.focus();
    }, reduced ? 0 : MOVE_MS);
  }, []);

  const setMascot = useCallback((next: MascotState, holdMs?: number) => {
    window.clearTimeout(holdTimer.current);
    setState(next);
    if (holdMs) holdTimer.current = window.setTimeout(() => setState("idle"), holdMs);
  }, []);

  useEffect(() => () => { window.clearTimeout(holdTimer.current); window.clearTimeout(motionTimer.current); }, []);
  // Closed panel: off screen except its handle; its content must not be reachable by keyboard.
  useEffect(() => {
    panelRef.current?.querySelectorAll<HTMLElement>(".qf-head, .qf-log, .qf-form").forEach(el => { el.inert = !open; });
  }, [open]);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }); }, [messages]);
  useEffect(() => {
    if (!open) return;
    setAttention(false);
    const onKey = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  async function send(e?: FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setMessages(m => [...m, { id: Date.now(), who: "user", text }]);
    setMascot("thinking");
    let response: QFitResponse;
    try {
      response = await askQFit(text, history.current, { ...context, locale: language });
    } catch {
      response = { success: false, message: t.network, data: {}, actions: [], uncertainty: [], sources: [],
                   media: [], evidence: [], message_source: "system", intent: "error" } as unknown as QFitResponse;
    }
    // Typewriter reveal while the speaking animation plays.
    const full = response.message || response.error?.message || "";
    const id = Date.now() + 1;
    setMascot("speaking");
    setMessages(m => [...m, { id, who: "bot", text: "" }]);
    const step = Math.max(1, Math.ceil(full.length / (MAX_SPEAK_MS / CHAR_MS)));
    for (let i = step; i < full.length + step; i += step) {
      const shown = full.slice(0, i);
      setMessages(m => m.map(x => (x.id === id ? { ...x, text: shown } : x)));
      await new Promise(r => setTimeout(r, CHAR_MS));
    }
    setMessages(m => m.map(x => (x.id === id ? { ...x, text: full, response } : x)));
    history.current.push({ role: "user", content: text });
    if (response.success && full) history.current.push({ role: "assistant", content: full.slice(0, 4000) });
    const settled = settleState(response);
    setMascot(settled.state, settled.holdMs);
    if (!openRef.current) setAttention(true);
    setBusy(false);
    onResponse?.(response);
    if (response.actions?.length) onActions?.(response.actions, response);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
  }

  return (
    <div className="qf-root" data-corner={corner} data-open={open} data-motion={motion ?? undefined}>
      <button className="qf-mascot" type="button" data-state={forceState ?? state} data-attention={attention}
              aria-label={t.open} aria-expanded={open} onClick={() => setOpen(o => !o)}>
        <span className="qf-art">
          <span className="qf-sprite" /><span className="qf-glow" /><span className="qf-twinkle" /><span className="qf-burst" />
        </span>
        <span className="qf-badge" aria-hidden="true" />
      </button>
      <aside className="qf-panel" role="dialog" aria-label="Q-FIT" aria-hidden={!open} ref={panelRef}>
        <button className="qf-handle" type="button" tabIndex={-1} aria-hidden="true" onClick={() => setOpen(o => !o)} />
        <header className="qf-head">
          <img src={robinIcon} alt="" />
          <div><div className="qf-title">Q-FIT</div><div className="qf-sub">{t.sub}</div></div>
          <button className="qf-close" type="button" aria-label={t.close} onClick={() => setOpen(false)}>&times;</button>
        </header>
        <div className="qf-log" ref={logRef} aria-live="polite">
          {messages.map(m => {
            const r = m.response;
            const sources = (r?.sources ?? []).filter(s => s.url).slice(0, 4);
            return (
              <div key={m.id} className={`qf-msg ${m.who}${r && r.message_source !== "ai_generated" ? " system" : ""}`}>
                <Rich text={m.text} />
                {r?.data?.fallback?.active && <div className="qf-note">{t.fallback}</div>}
                {r?.message_source === "ai_generated" && <div className="qf-note">{t.ai}</div>}
                {!!r?.uncertainty?.length && (
                  <details><summary>{t.caveats} ({r.uncertainty.length})</summary>
                    <ul>{r.uncertainty.slice(0, 6).map((u, i) => <li key={i}>{u}</li>)}</ul></details>)}
                {!!sources.length && (
                  <details><summary>{t.sources} ({sources.length})</summary>
                    <ul>{sources.map((s, i) => <li key={i}><a href={s.url} target="_blank" rel="noopener noreferrer">
                      {s.name ?? s.url}</a></li>)}</ul></details>)}
              </div>
            );
          })}
        </div>
        <form className="qf-form" onSubmit={send}>
          <textarea ref={inputRef} className="qf-input" rows={1} maxLength={2000} placeholder={t.placeholder}
                    value={input} onChange={e => setInput(e.target.value)} onKeyDown={onKeyDown} />
          <button className="qf-send" type="submit" disabled={busy}>{t.send}</button>
        </form>
      </aside>
    </div>
  );
}
