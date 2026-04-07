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
  const [events, setEvents] = useState<WebSocketEvent[]>([]);
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    if (!sessionId) return;
    const wsUrl =
      (process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000") +
      `/ws/${sessionId}`;

    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => setConnected(true);
    ws.current.onclose = () => setConnected(false);
    ws.current.onerror = () => setConnected(false);

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
      ws.current?.close();
    };
  }, [sessionId]);

  useEffect(() => {
    const cleanup = connect();
    return cleanup;
  }, [connect]);

  return { events, connected };
}
