/* Q-FIT assistant widget: reference implementation of the mascot state machine and chat panel.
   Talks to the real backend (POST /chat). The React component (mascot/react/src/qfit) follows the same rules:
   docs/MASCOT_AND_CHAT_UI.md.

   Mascot states:  idle -> thinking (request pending) -> speaking (answer being revealed)
                   -> found (real data came back, 1.2 s) | quiet (no data / fallback / error, 2.5 s) -> idle
   attention:      an answer arrived while the panel was closed (hop + badge until opened). */
(function () {
  "use strict";
  // Assets are found relative to this script (mascot/vanilla/ -> mascot/assets/), wherever the page is.
  const ASSETS = new URL("../assets/", (document.currentScript && document.currentScript.src) || location.href).href;

  const TEXT = {
    tr: { open: "Q-FIT asistanını aç", close: "Kapat", title: "Q-FIT", sub: "SPHEREx araştırma asistanı",
          placeholder: "Bir soru sor... (ör. Andromeda'yı göster)", send: "Gönder",
          hello: "Merhaba, ben Q-FIT. SPHEREx verisini bulmana ve neyin söylenip neyin söylenemeyeceğini anlamana yardım ederim.",
          caveats: "Belirsizlikler", sources: "Kaynaklar", fallback: "Yapay zekâ şu an kullanılamıyor; yanıt bilgi tabanından alındı.",
          network: "Sunucuya ulaşılamadı. Bağlantıyı kontrol edip tekrar dene.", aiText: "Yapay zekâ açıklaması" },
    en: { open: "Open the Q-FIT assistant", close: "Close", title: "Q-FIT", sub: "SPHEREx research assistant",
          placeholder: "Ask something... (e.g. show me Andromeda)", send: "Send",
          hello: "Hi, I am Q-FIT. I help you find SPHEREx data and understand what it can and cannot tell you.",
          caveats: "Caveats", sources: "Sources", fallback: "The AI is unavailable right now; this answer comes from the knowledge base.",
          network: "The server could not be reached. Check the connection and try again.", aiText: "AI explanation" },
  };
  const FOUND_MS = 1200, QUIET_MS = 2500, CHAR_MS = 18, MAX_SPEAK_MS = 4000, HISTORY = 10;
  const MOVE_MS = 180 + 600;   // grab + pull, as --qf-grab-ms + --qf-pull-ms in the CSS

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  // Minimal, safe rendering: escape everything, then allow **bold** only.
  const render = s => escapeHtml(s).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  class QFitWidget {
    constructor(root, opts = {}) {
      this.root = root;
      this.api = (opts.api || "").replace(/\/$/, "");
      this.lang = opts.lang || ((navigator.language || "tr").startsWith("tr") ? "tr" : "en");
      this.t = TEXT[this.lang];
      this.history = [];
      this.context = opts.context || {};          // what the host view shows: ra, dec, fov_deg, selected_object...
      this.timers = [];
      root.classList.add("qf-root");
      root.dataset.corner = opts.corner || root.dataset.corner || "bottom-right";
      root.dataset.open = "false";
      root.innerHTML = `
        <button class="qf-mascot" type="button" data-state="idle" aria-label="${this.t.open}" aria-expanded="false">
          <span class="qf-art"><span class="qf-sprite"></span><span class="qf-glow"></span>
            <span class="qf-twinkle"></span><span class="qf-burst"></span></span>
          <span class="qf-badge" aria-hidden="true"></span>
        </button>
        <aside class="qf-panel" role="dialog" aria-label="Q-FIT" aria-hidden="true">
          <button class="qf-handle" type="button" tabindex="-1" aria-hidden="true"></button>
          <header class="qf-head">
            <img src="${ASSETS}icons/robin_64.png" alt="">
            <div><div class="qf-title">${this.t.title}</div><div class="qf-sub">${this.t.sub}</div></div>
            <button class="qf-close" type="button" aria-label="${this.t.close}">&times;</button>
          </header>
          <div class="qf-log" aria-live="polite"></div>
          <form class="qf-form">
            <textarea class="qf-input" rows="1" maxlength="2000" placeholder="${this.t.placeholder}"></textarea>
            <button class="qf-send" type="submit">${this.t.send}</button>
          </form>
        </aside>`;
      this.mascot = root.querySelector(".qf-mascot");
      this.panel = root.querySelector(".qf-panel");
      this.log = root.querySelector(".qf-log");
      this.input = root.querySelector(".qf-input");
      this.sendBtn = root.querySelector(".qf-send");
      this.mascot.addEventListener("click", () => this.toggle());
      root.querySelector(".qf-close").addEventListener("click", () => this.toggle(false));
      root.querySelector(".qf-handle").addEventListener("click", () => this.toggle());
      this.inside = [...root.querySelectorAll(".qf-head, .qf-log, .qf-form")];
      this.inside.forEach(el => { el.inert = true; });
      root.querySelector(".qf-form").addEventListener("submit", e => { e.preventDefault(); this.send(); });
      this.input.addEventListener("keydown", e => {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); this.send(); }
      });
      document.addEventListener("keydown", e => { if (e.key === "Escape" && this.isOpen) this.toggle(false); });
      this.bubble("bot", render(this.t.hello));
    }

    get isOpen() { return this.root.dataset.open === "true"; }
    setCorner(corner) { this.root.dataset.corner = corner; }
    setContext(ctx) { this.context = { ...ctx }; }

    setState(state, holdMs) {
      this.timers.forEach(clearTimeout);
      this.timers = [];
      this.mascot.dataset.state = state;
      if (holdMs) this.timers.push(setTimeout(() => this.setState("idle"), holdMs));
    }

    // The robin pulls the panel open with its beak (or pushes it shut); CSS does the motion,
    // data-motion marks how long it lasts.
    toggle(open = !this.isOpen) {
      if (open === this.isOpen) return;
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      clearTimeout(this.motionTimer);
      if (!reduced) this.root.dataset.motion = open ? "opening" : "closing";
      this.root.dataset.open = String(open);
      this.mascot.setAttribute("aria-expanded", String(open));
      this.panel.setAttribute("aria-hidden", String(!open));
      this.inside.forEach(el => { el.inert = !open; });
      this.motionTimer = setTimeout(() => {
        delete this.root.dataset.motion;
        if (open) this.input.focus();
      }, reduced ? 0 : MOVE_MS);
      if (open) this.mascot.dataset.attention = "false";
    }

    bubble(who, html, extraClass = "") {
      const el = document.createElement("div");
      el.className = `qf-msg ${who} ${extraClass}`.trim();
      el.innerHTML = html;
      this.log.appendChild(el);
      this.log.scrollTop = this.log.scrollHeight;
      return el;
    }

    async send() {
      const text = this.input.value.trim();
      if (!text || this.sendBtn.disabled) return;
      this.input.value = "";
      this.bubble("user", escapeHtml(text));
      this.sendBtn.disabled = true;
      this.setState("thinking");
      let body;
      try {
        const res = await fetch(`${this.api}/chat`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, history: this.history.slice(-HISTORY),
                                 context: { ...this.context, locale: this.lang } }),
        });
        body = await res.json();             // errors also come back as the Q-FIT envelope
      } catch (err) {
        body = { success: false, message: this.t.network, error: { code: "network" }, data: {} };
      }
      this.sendBtn.disabled = false;
      await this.reveal(body);
      this.history.push({ role: "user", content: text });
      if (body.success && body.message) this.history.push({ role: "assistant", content: body.message.slice(0, 4000) });
      if (!this.isOpen) this.mascot.dataset.attention = "true";
      this.dispatch(body);
    }

    // Typewriter reveal while the speaking animation plays.
    async reveal(body) {
      const data = body.data || {};
      const system = body.message_source !== "ai_generated";
      const el = this.bubble("bot", "", system ? "system" : "");
      const message = body.message || (body.error && body.error.message) || "";
      this.setState("speaking");
      const step = Math.max(1, Math.ceil(message.length / (MAX_SPEAK_MS / CHAR_MS)));
      for (let i = step; i < message.length + step; i += step) {
        el.innerHTML = render(message.slice(0, i));
        this.log.scrollTop = this.log.scrollHeight;
        await new Promise(r => setTimeout(r, CHAR_MS));
      }
      let extra = "";
      if (data.fallback && data.fallback.active) extra += `<div class="qf-note">${this.t.fallback}</div>`;
      if (body.message_source === "ai_generated") extra += `<div class="qf-note">${this.t.aiText}</div>`;
      if ((body.uncertainty || []).length) {
        extra += `<details><summary>${this.t.caveats} (${body.uncertainty.length})</summary><ul>` +
          body.uncertainty.slice(0, 6).map(u => `<li>${escapeHtml(u)}</li>`).join("") + "</ul></details>";
      }
      const sources = (body.sources || []).filter(s => s.url).slice(0, 4);
      if (sources.length) {
        extra += `<details><summary>${this.t.sources} (${sources.length})</summary><ul>` +
          sources.map(s => `<li><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">` +
                           `${escapeHtml(s.name || s.url)}</a></li>`).join("") + "</ul></details>";
      }
      el.innerHTML = render(message) + extra;
      this.log.scrollTop = this.log.scrollHeight;
    }

    // The final state after speaking, chosen from the response envelope.
    dispatch(body) {
      const data = body.data || {};
      if (!body.success || (data.fallback && data.fallback.active) || data.spherex_available === false
          || (data.tool_errors || []).length || body.intent === "error") {
        this.setState("quiet", QUIET_MS);
      } else if (data.spherex_available === true || (body.media || []).length) {
        this.setState("found", FOUND_MS);
      } else {
        this.setState("idle");
      }
      // A real app would also run body.actions here (focus_map, display_image, ...).
      this.root.dispatchEvent(new CustomEvent("qfit:response", { detail: body }));
    }
  }

  window.QFitWidget = QFitWidget;
})();
