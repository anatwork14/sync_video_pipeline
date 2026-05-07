"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface WebSocketEvent {
  type: string;
  session_id: string;
  chunk_index?: number;
  cam_id?: string;
  url?: string;
  message?: string;
}

export function useWebSocket(sessionId: string | null) {
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [events, setEvents] = useState<WebSocketEvent[]>([]);
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    if (!sessionId) return;

    // Derive WebSocket URL from the current page's host.
    // This works correctly both on localhost AND through Cloudflare tunnel
    // without needing a baked NEXT_PUBLIC_WS_URL env var.
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    let wsHost = window.location.host;
    // If accessing frontend directly on port 3000, route WS to backend port 8000
    if (window.location.port === "3000") {
      wsHost = `${window.location.hostname}:8000`;
    }
    const wsUrl = `${wsProtocol}//${wsHost}/ws/${sessionId}`;

    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      setConnected(true);
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };

    ws.current.onclose = () => {
      setConnected(false);
      // Auto-reconnect with 3s backoff
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.current.onerror = () => {
      ws.current?.close();
    };

    ws.current.onmessage = (e) => {
      try {
        const event: WebSocketEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev.slice(-49), event]); // keep last 50
      } catch {}
    };

    // Send heartbeat every 25s
    const ping = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send('{"action":"ping"}');
      }
    }, 25000);

    return () => {
      clearInterval(ping);
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      ws.current?.close();
    };
  }, [sessionId]);

  useEffect(() => {
    const cleanup = connect();
    // connect() returns undefined when sessionId is null — guard it
    return () => { if (cleanup) cleanup(); };
  }, [connect]);

  return { events, connected };
}
