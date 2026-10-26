import { useEffect, useRef, useState } from "react";

import { parseProductPresentations, ProductPresentations } from "@/lib/product-presentations";
import { Message } from "@/lib/types";
import { arrayBufferToBase64, base64ToArrayBuffer } from "@/lib/utils";
import { getWebsocketBaseUrl } from "@/lib/api";

export type ImageSearchState =
  | { kind: "idle" }
  | { kind: "pending"; requestId: string }
  | { kind: "error"; message: string; retryable: boolean }
  | { kind: "complete"; status: "matched" | "no_match" };

export type ConnectionState =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "open" }
  | { kind: "error"; reason: "auth" | "network"; message: string };

/** Map server-side rejection messages to something a customer can act on. */
export function describeConnectionError(serverMessage: unknown): ConnectionState {
  const text = typeof serverMessage === "string" ? serverMessage : "";
  if (/api key|authentication|invalid token|access/i.test(text)) {
    return { kind: "error", reason: "auth", message: "แชตนี้ยังไม่พร้อมใช้งาน กรุณาติดต่อผู้ดูแลเว็บไซต์" };
  }
  return { kind: "error", reason: "network", message: "เชื่อมต่อกับผู้ช่วยไม่สำเร็จ ตรวจสอบอินเทอร์เน็ตแล้วลองอีกครั้ง" };
}

export function useWebsocket({
  url,
  apiKey,
  onNewAudio,
  onAudioDone,
  enabled = true,
  inlineErrors = false,
}: {
  url?: string;
  apiKey?: string;
  onNewAudio?: (audio: Int16Array<ArrayBuffer>) => void;
  onAudioDone?: () => void;
  /** When false no socket is opened (e.g. the admin theme preview). */
  enabled?: boolean;
  /** Report server rejections through `connection` instead of window.alert. */
  inlineErrors?: boolean;
} = {}) {
  const defaultWs = getWebsocketBaseUrl();

  // Add API key to URL if provided
  let wsUrl = url ?? defaultWs;
  if (apiKey) {
    const separator = wsUrl.includes('?') ? '&' : '?';
    wsUrl = `${wsUrl}${separator}api_key=${encodeURIComponent(apiKey)}`;
  }

  url = wsUrl;
  const [imageSearchAvailable, setImageSearchAvailable] = useState(false);
  const [imageSearchState, setImageSearchState] = useState<ImageSearchState>({ kind: "idle" });
  const [imageComposerEpoch, setImageComposerEpoch] = useState(0);
  const imageRequest = useRef<string | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [history, setHistory] = useState<Message[]>([]);
  const [presentations, setPresentations] = useState<ProductPresentations>({});
  const [productActionError, setProductActionError] = useState<string | null>(null);
  const [agentName, setAgentName] = useState<string | null>(null);
  const websocket = useRef<WebSocket | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [voiceResponseEnabled, setVoiceResponseEnabled] = useState(true);
  const [connection, setConnection] = useState<ConnectionState>({ kind: enabled ? "connecting" : "idle" });
  const [attempt, setAttempt] = useState(0);
  const reconnect = () => setAttempt((value) => value + 1);

  useEffect(() => {
    if (!enabled) {
      setConnection({ kind: "idle" });
      return;
    }
    setConnection({ kind: "connecting" });
    let rejected = false;
    imageRequest.current = null;
    setImageSearchAvailable(false);
    setImageSearchState({ kind: "idle" });
    setImageComposerEpoch((value) => value + 1);
    setHistory([]);
    setPresentations({});
    setProductActionError(null);
    setIsReady(false);
    setIsLoading(false);
    setAgentName(null);
    const ws = new WebSocket(url);
    ws.addEventListener("open", () => {
      if (websocket.current !== ws) return;
      setIsReady(true);
      setConnection({ kind: "open" });
    });
    ws.addEventListener("close", () => {
      if (websocket.current !== ws) return;
      if (!rejected) setConnection(describeConnectionError(null));
      setIsReady(false);
      setIsLoading(false);
      if (imageRequest.current) setImageSearchState({ kind: "error", message: "การเชื่อมต่อขัดข้อง กรุณาเชื่อมต่อใหม่", retryable: true });
      imageRequest.current = null;
    });
    ws.addEventListener("error", (event) => {
      if (websocket.current !== ws) return;
      if (!rejected) setConnection(describeConnectionError(null));
      setIsReady(false);
      setIsLoading(false);
      imageRequest.current = null;
      setImageSearchState({ kind: "error", message: "การเชื่อมต่อขัดข้อง กรุณาเชื่อมต่อใหม่", retryable: true });
      console.error("Websocket error", event);
    });
    ws.addEventListener("message", (event) => {
      if (websocket.current !== ws) return;
      const data = JSON.parse(event.data);
      if (data.type === "knowledge.image.result" || data.type === "knowledge.image.error") {
        if (!imageRequest.current || data.request_id !== imageRequest.current) return;
        imageRequest.current = null;
        setIsLoading(false);
        if (data.type === "knowledge.image.error" || data.status === "unavailable") {
          setImageSearchState({ kind: "error", message: typeof data.message === "string" ? data.message : "การค้นหาด้วยรูปภาพยังไม่พร้อมใช้งาน", retryable: data.retryable !== false });
        } else if (data.status === "matched" || data.status === "no_match") {
          setImageSearchState({ kind: "complete", status: data.status });
        }
        return;
      }
      if (data.type === "product.action.error") {
        setProductActionError(typeof data.message === "string" ? data.message : "ไม่สามารถสอบถามสินค้านี้ได้");
        setIsLoading(false);
        return;
      }
      if (data.type === "error") {
        console.error("WebSocket Error:", data.message);
        if (inlineErrors) {
          rejected = true;
          setConnection(describeConnectionError(data.message));
        } else {
          alert(data.message); // Alert the user
        }
        setIsLoading(false);
        return;
      }

      // Handle session config from server
      if (data.type === "session.config") {
        setImageSearchAvailable(data.knowledge_image_search_enabled === true);
        if (typeof data.voice_response_enabled === "boolean") {
          setVoiceResponseEnabled(data.voice_response_enabled);
        }
        return;
      }

      if (data.type === "history.updated") {
        if (data.reason === "knowledge.image.result" && (!imageRequest.current || data.request_id !== imageRequest.current)) return;
        if (["response.done", "assistant.message", "admin.message"].includes(data.reason) || data.inputs.length === 0) {
          setIsLoading(false);
        }
        setHistory(data.inputs);
        setPresentations(parseProductPresentations(data.presentations));
        if (data.agent_name) {
          setAgentName(data.agent_name);
        }
      } else if (data.type === "response.audio.delta") {
        const audioData = new Int16Array(base64ToArrayBuffer(data.delta));
        if (typeof onNewAudio === "function") {
          onNewAudio(audioData);
        }
      } else if (data.type === "audio.done") {
        if (typeof onAudioDone === "function") {
          onAudioDone();
        }
      }
    });

    websocket.current = ws;
    return () => {
      ws.close();
      if (websocket.current === ws) websocket.current = null;
    };
  }, [url, onNewAudio, onAudioDone, enabled, inlineErrors, attempt]);

  function sendTextMessage(message: string) {
    if (websocket.current?.readyState !== WebSocket.OPEN || isLoading) return;
    setProductActionError(null);
    setIsLoading(true);
    const newHistory = [
      ...history,
      {
        role: "user",
        content: message,
        type: "message",
      } satisfies Message,
    ];
    setHistory(newHistory);
    websocket.current?.send(
      JSON.stringify({
        type: "history.update",
        inputs: newHistory,
      })
    );
  }

  function sendProductInquiry(callId: string, productId: string) {
    if (websocket.current?.readyState !== WebSocket.OPEN || isLoading) return;
    setProductActionError(null);
    setIsLoading(true);
    websocket.current.send(JSON.stringify({ type: "product.inquire", call_id: callId, product_id: productId }));
  }

  function sendImageSearch(image: { mime: "image/jpeg" | "image/png"; base64: string }, query = ""): boolean {
    query = query.trim();
    if (query.length > 2000) return false;
    if (websocket.current?.readyState !== WebSocket.OPEN || isLoading || imageRequest.current || !imageSearchAvailable) return false;
    const requestId = crypto.randomUUID();
    imageRequest.current = requestId;
    setImageSearchState({ kind: "pending", requestId });
    setProductActionError(null);
    setIsLoading(true);
    try {
      websocket.current.send(JSON.stringify({ type: "knowledge.image.search", request_id: requestId, image, ...(query ? { query } : {}) }));
      return true;
    } catch {
      imageRequest.current = null;
      setIsLoading(false);
      setImageSearchState({ kind: "error", message: "ส่งรูปภาพไม่สำเร็จ กรุณาลองใหม่", retryable: true });
      return false;
    }
  }

  function sendKnowledgeInquiry(messageId: string, cardId: string) {
    if (websocket.current?.readyState !== WebSocket.OPEN || isLoading || imageRequest.current) return;
    setProductActionError(null);
    setIsLoading(true);
    websocket.current.send(JSON.stringify({ type: "knowledge.product.inquire", message_id: messageId, card_id: cardId }));
  }

  function resetHistory() {
    imageRequest.current = null;
    setImageSearchState({ kind: "idle" });
    setImageComposerEpoch((value) => value + 1);
    setPresentations({});
    setProductActionError(null);
    setHistory([]);
    setIsLoading(false);
    setAgentName(null);
    websocket.current?.send(
      JSON.stringify({
        type: "history.update",
        inputs: [],
        reset_agent: true,
      })
    );
  }
  function sendAudioMessage(audio: Int16Array<ArrayBuffer>) {
    if (!websocket.current) {
      throw new Error("Websocket not connected");
    }
    websocket.current.send(
      JSON.stringify({
        type: "history.update",
        inputs: history,
      })
    );
    websocket.current.send(
      JSON.stringify({
        type: "input_audio_buffer.append",
        delta: arrayBufferToBase64(audio.buffer),
      })
    );
    websocket.current.send(
      JSON.stringify({
        type: "input_audio_buffer.commit",
      })
    );
  }

  return {
    isReady,
    connection,
    reconnect,
    imageSearchAvailable,
    imageSearchState,
    imageComposerEpoch,
    sendImageSearch,
    sendKnowledgeInquiry,
    sendTextMessage,
    sendProductInquiry,
    presentations,
    productActionError,
    sendAudioMessage,
    history,
    resetHistory,
    agentName,
    isLoading,
    voiceResponseEnabled,
  };
}
