import type { WSMessage } from '../types';

type MessageHandler = (msg: WSMessage) => void;
type ConnectionHandler = (connected: boolean) => void;

// ─── WebSocket Service ───────────────────────────────────────────────────────

class WebSocketService {
  private ws: WebSocket | null = null;
  private handlers = new Set<MessageHandler>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 2000;
  private maxDelay = 30000;
  private url: string;
  private _connected = false;
  private intentionalClose = false;

  onConnectionChange: ConnectionHandler | null = null;

  constructor(url: string) {
    this.url = url;
  }

  get connected() {
    return this._connected;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    this.intentionalClose = false;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this._connected = true;
        this.reconnectDelay = 2000;
        this.onConnectionChange?.(true);
        console.info('[WS] Connected to', this.url);

        // Send periodic ping to keep alive
        const ping = setInterval(() => {
          if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send('ping');
          } else {
            clearInterval(ping);
          }
        }, 25000);
      };

      this.ws.onmessage = (event) => {
        // Ignore pong responses
        if (event.data === 'pong') return;
        try {
          const msg: WSMessage = JSON.parse(event.data);
          this.handlers.forEach((h) => h(msg));
        } catch (e) {
          console.error('[WS] Failed to parse message:', e);
        }
      };

      this.ws.onclose = () => {
        this._connected = false;
        this.onConnectionChange?.(false);
        if (!this.intentionalClose) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = () => {
        // onerror is always followed by onclose
        this.ws?.close();
      };
    } catch (e) {
      console.error('[WS] Failed to create WebSocket:', e);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    console.info(`[WS] Reconnecting in ${this.reconnectDelay / 1000}s…`);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxDelay);
      this.connect();
    }, this.reconnectDelay);
  }

  subscribe(handler: MessageHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  disconnect(): void {
    this.intentionalClose = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}

// ─── Singleton Instance ───────────────────────────────────────────────────────

const WS_URL =
  import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/alerts';

export const wsService = new WebSocketService(WS_URL);
