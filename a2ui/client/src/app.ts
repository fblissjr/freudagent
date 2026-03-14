/**
 * FreudAgent A2UI application -- Lit-based client that renders
 * LLM-generated A2UI surfaces via the @a2ui/lit renderer.
 */

import { SignalWatcher } from "@lit-labs/signals";
import { provide } from "@lit/context";
import { LitElement, html, css, nothing, unsafeCSS } from "lit";
import { customElement, state } from "lit/decorators.js";
import { v0_8 } from "@a2ui/lit";
import * as UI from "@a2ui/lit/ui";
import { darkTheme } from "./theme.js";
import * as api from "./api.js";

const SURFACES = [
  { id: "dashboard", label: "Dashboard" },
  { id: "extraction_list", label: "Extractions" },
  { id: "session_timeline", label: "Sessions" },
  { id: "feedback_summary", label: "Feedback" },
];

@customElement("freudagent-app")
export class FreudAgentApp extends SignalWatcher(LitElement) {
  @provide({ context: UI.Context.themeContext })
  accessor theme: v0_8.Types.Theme = darkTheme;

  #processor = v0_8.Data.createSignalA2uiMessageProcessor();

  @state() accessor currentSurface = "dashboard";
  @state() accessor loading = false;
  @state() accessor error: string | null = null;
  @state() accessor provider = "echo";
  @state() accessor lastModel = "";

  static styles = [
    unsafeCSS(v0_8.Styles.structuralStyles),
    css`
      :host {
        display: flex;
        flex-direction: column;
        min-height: 100vh;
        background: #0d1117;
        color: #e6edf3;
        font-family: "Roboto", sans-serif;
      }

      header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 24px;
        border-bottom: 1px solid #30363d;
        background: #161b22;
        flex-shrink: 0;
      }

      header h1 {
        font-size: 16px;
        font-weight: 600;
        margin: 0;
      }

      .header-right {
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 12px;
        color: #8b949e;
      }

      .header-right select {
        background: #0d1117;
        color: #e6edf3;
        border: 1px solid #30363d;
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 12px;
      }

      nav {
        display: flex;
        gap: 4px;
        padding: 8px 24px;
        border-bottom: 1px solid #30363d;
        background: #161b22;
        flex-shrink: 0;
      }

      nav button {
        padding: 6px 16px;
        border: 1px solid #30363d;
        border-radius: 6px;
        background: transparent;
        color: #8b949e;
        font-size: 13px;
        cursor: pointer;
        transition: all 0.15s;
      }

      nav button:hover {
        color: #e6edf3;
        border-color: #8b949e;
      }

      nav button.active {
        color: #58a6ff;
        border-color: #58a6ff;
        background: rgba(88, 166, 255, 0.1);
      }

      main {
        flex: 1;
        padding: 24px;
        overflow-y: auto;
      }

      .surface-container {
        max-width: 960px;
        margin: 0 auto;
      }

      .status {
        font-size: 12px;
        color: #8b949e;
      }

      .status.connected {
        color: #3fb950;
      }

      .status.error {
        color: #f85149;
      }

      .loading {
        text-align: center;
        padding: 80px 24px;
        color: #8b949e;
      }

      .error-state {
        text-align: center;
        padding: 80px 24px;
        color: #f85149;
      }

      .error-state h2 {
        font-size: 18px;
        margin-bottom: 8px;
      }

      .error-state p {
        font-size: 14px;
        color: #8b949e;
      }
    `,
  ];

  connectedCallback() {
    super.connectedCallback();
    this.#loadSurface("dashboard");
  }

  async #loadSurface(surface: string) {
    this.currentSurface = surface;
    this.loading = true;
    this.error = null;

    try {
      const result = await api.compose(surface, {}, this.provider);

      if (result.valid && result.messages) {
        this.#processor.processMessages(result.messages);
        this.lastModel = result.model || this.provider;
      } else if (result.error) {
        this.error = result.error;
      } else if (result.errors) {
        this.error = "Validation: " + result.errors.join(", ");
      }
    } catch (err) {
      this.error = `Failed to load: ${err}`;
    } finally {
      this.loading = false;
    }
  }

  #renderSurface(surfaceId: string) {
    const surface = this.#processor.getSurfaces().get(surfaceId);
    if (!surface) return nothing;
    return html`
      <a2ui-surface
        .surface=${{ ...surface }}
        .surfaceId=${surfaceId}
        .processor=${this.#processor}
        @a2uiaction=${(e: any) => this.#handleAction(e, surfaceId)}
      ></a2ui-surface>
    `;
  }

  async #handleAction(evt: any, surfaceId: string) {
    const { action, dataContextPath, sourceComponent } = evt.detail;

    const context: Record<string, any> = {};
    if (action.context) {
      for (const item of action.context) {
        if (item.value.literalBoolean !== undefined)
          context[item.key] = item.value.literalBoolean;
        else if (item.value.literalNumber !== undefined)
          context[item.key] = item.value.literalNumber;
        else if (item.value.literalString !== undefined)
          context[item.key] = item.value.literalString;
        else if (item.value.path) {
          const path = this.#processor.resolvePath(
            item.value.path,
            dataContextPath,
          );
          context[item.key] = this.#processor.getData(
            sourceComponent,
            path,
            surfaceId,
          );
        }
      }
    }

    try {
      const result = await api.sendAction(
        { name: action.name, context },
        this.provider,
      );
      if (result.success && result.messages) {
        this.#processor.processMessages(result.messages);
      } else if (result.success) {
        // Reload current surface after a state-changing action
        await this.#loadSurface(this.currentSurface);
      }
    } catch (err) {
      console.error("Action failed:", err);
    }
  }

  #onNavClick(surface: string) {
    this.#loadSurface(surface);
  }

  #onProviderChange(e: Event) {
    this.provider = (e.target as HTMLSelectElement).value;
    this.#loadSurface(this.currentSurface);
  }

  render() {
    return html`
      <header>
        <h1>FreudAgent A2UI</h1>
        <div class="header-right">
          <select @change=${this.#onProviderChange}>
            <option value="echo" ?selected=${this.provider === "echo"}>
              Echo
            </option>
            <option value="claude" ?selected=${this.provider === "claude"}>
              Claude
            </option>
            <option value="gemini" ?selected=${this.provider === "gemini"}>
              Gemini
            </option>
          </select>
          <span class="status ${this.error ? "error" : this.loading ? "" : "connected"}">
            ${this.loading ? "loading..." : this.error ? "error" : this.lastModel || "ready"}
          </span>
        </div>
      </header>
      <nav>
        ${SURFACES.map(
          (s) => html`
            <button
              class=${this.currentSurface === s.id ? "active" : ""}
              @click=${() => this.#onNavClick(s.id)}
            >
              ${s.label}
            </button>
          `,
        )}
      </nav>
      <main>
        <div class="surface-container">
          ${this.loading
            ? html`<div class="loading">Loading surface...</div>`
            : this.error
              ? html`
                  <div class="error-state">
                    <h2>Error</h2>
                    <p>${this.error}</p>
                  </div>
                `
              : this.#renderSurfaceContent()}
        </div>
      </main>
    `;
  }

  #renderSurfaceContent() {
    const surfaces = this.#processor.getSurfaces();
    if (surfaces.size === 0) {
      return html`<div class="loading">No surface loaded</div>`;
    }

    // Try the requested surface first, fall back to first available
    if (surfaces.has(this.currentSurface)) {
      return this.#renderSurface(this.currentSurface);
    }
    const firstId = surfaces.keys().next().value;
    return this.#renderSurface(firstId!);
  }
}
