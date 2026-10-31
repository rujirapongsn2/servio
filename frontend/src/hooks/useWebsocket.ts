import { useEffect, useRef, useState } from "react";

import { parseProductPresentations, ProductPresentations } from "@/lib/product-presentations";
import { SUPPORTED_CATALOGS, parseA2uiSnapshots, discoveryActionEnvelope, type A2uiSurfaces, type DiscoveryAction } from "@/lib/a2ui-discovery";
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
  const discoveryRequest = useRef<string | null>(null);
  const videoRequest = useRef<string | null>(null);
  const [videoUploadToken, setVideoUploadToken] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [history, setHistory] = useState<Message[]>([]);
  const [a2uiSurfaces, setA2uiSurfaces] = useState<A2uiSurfaces>({});
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
      setVideoUploadToken(null);
      videoRequest.current = null;
      setConnection({ kind: "idle" });
      return;
    }
    setConnection({ kind: "connecting" });
    let rejected = false;
    imageRequest.current = null;
    discoveryRequest.current = null;
    setImageSearchAvailable(false);
    setVideoUploadToken(null);
    videoRequest.current = null;
    setImageSearchState({ kind: "idle" });
    setImageComposerEpoch((value) => value + 1);
    setHistory([]);
    setPresentations({});
    setA2uiSurfaces({});
    setProductActionError(null);
    setIsReady(false);
    setIsLoading(false);
    setAgentName(null);
    const ws = new WebSocket(url);
    let videoGrantAvailable = false;
    const grantRefresh = setInterval(() => {
      if (websocket.current === ws && ws.readyState === WebSocket.OPEN && videoGrantAvailable) {
        try { ws.send(JSON.stringify({ type: "knowledge.video.refresh" })); } catch {}
      }
    }, 30 * 60 * 1000);
    ws.addEventListener("open", () => {
      if (websocket.current !== ws) return;
      ws.send(JSON.stringify({ type: "a2ui.capabilities", a2uiClientCapabilities: { supportedCatalogIds: SUPPORTED_CATALOGS } }));
      setIsReady(true);
      setConnection({ kind: "open" });
    });
    ws.addEventListener("close", () => {
      if (websocket.current !== ws) return;
      if (!rejected) setConnection(describeConnectionError(null));
      setIsReady(false);
      setVideoUploadToken(null);
      videoRequest.current = null;
      setIsLoading(false);
      if (imageRequest.current) setImageSearchState({ kind: "error", message: "การเชื่อมต่อขัดข้อง กรุณาเชื่อมต่อใหม่", retryable: true });
      imageRequest.current = null;
    });
    ws.addEventListener("error", (event) => {
      if (websocket.current !== ws) return;
      if (!rejected) setConnection(describeConnectionError(null));
      setIsReady(false);
      setVideoUploadToken(null);
      videoRequest.current = null;
      setIsLoading(false);
      imageRequest.current = null;
      setImageSearchState({ kind: "error", message: "การเชื่อมต่อขัดข้อง กรุณาเชื่อมต่อใหม่", retryable: true });
      console.error("Websocket error", event);
    });
    ws.addEventListener("message", (event) => {
      if (websocket.current !== ws) return;
      const data = JSON.parse(event.data);
      if (data.type === "knowledge.video.error") {
        if (!videoRequest.current || data.request_id !== videoRequest.current) return;
        videoRequest.current = null;
        setIsLoading(false);
        setProductActionError(typeof data.message === "string" ? data.message : "วิเคราะห์วิดีโอไม่สำเร็จ กรุณาลองใหม่");
        return;
      }
      if (data.type === "knowledge.image.result" || data.type === "knowledge.image.error") {
        if (!imageRequest.current || data.request_id !== imageRequest.current) return;
        imageRequest.current = null;
        setIsLoading(false);
        if (discoveryRequest.current === data.request_id) {
          discoveryRequest.current = null;
          if (data.type === "knowledge.image.error" || data.status === "unavailable") setProductActionError(typeof data.message === "string" ? data.message : "ปรับผลค้นหาไม่สำเร็จ กรุณาลองอีกครั้ง");
          return;
        }
        if (data.type === "knowledge.image.error" || data.status === "unavailable") {
          setImageSearchState({ kind: "error", message: typeof data.message === "string" ? data.message : "การค้นหาด้วยรูปภาพยังไม่พร้อมใช้งาน", retryable: data.retryable !== false });
        } else if (data.status === "matched" || data.status === "no_match") {
          setImageSearchState({ kind: "complete", status: data.status });
        }
        return;
      }
      if (data.type === "product.action.error") {
        imageRequest.current = null;
        discoveryRequest.current = null;
        setProductActionError(typeof data.message === "string" ? data.message : "ไม่สามารถสอบถามสินค้านี้ได้");
        setIsLoading(false);
        return;
      }
      if (data.type === "error") {
        setVideoUploadToken(null);
        videoRequest.current = null;
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
        videoGrantAvailable = data.knowledge_video_enabled === true && typeof data.video_upload_token === "string" && data.video_upload_token.length > 0;
        setVideoUploadToken(videoGrantAvailable ? data.video_upload_token : null);
        if (typeof data.voice_response_enabled === "boolean") {
          setVoiceResponseEnabled(data.voice_response_enabled);
        }
        return;
      }

      if (data.type === "history.updated") {
        if (data.reason === "response.done" && typeof data.request_id === "string" && data.request_id !== videoRequest.current) return;
        if (data.reason === "knowledge.image.result" && (!imageRequest.current || data.request_id !== imageRequest.current)) return;
        if (["response.done", "assistant.message", "admin.message"].includes(data.reason) || data.inputs.length === 0) {
          discoveryRequest.current = null;
          setIsLoading(false);
          videoRequest.current = null;
        }
        setHistory(data.inputs);
        setPresentations(parseProductPresentations(data.presentations));
        if (data.a2ui !== undefined || data.inputs.length === 0) setA2uiSurfaces(parseA2uiSnapshots(data.a2ui));
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
      clearInterval(grantRefresh);
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

  function sendDiscoveryAction(surfaceId: string, action: DiscoveryAction): boolean {
    const surface = a2uiSurfaces[surfaceId];
    if (!surface || surface.kind !== "discovery" || !surface.active || websocket.current?.readyState !== WebSocket.OPEN || isLoading || imageRequest.current || videoRequest.current || discoveryRequest.current) return false;
    if (action.name === "discovery.inquire" && !surface.products.some(product => product.id === action.context.card_id)) return false;
    const envelope = discoveryActionEnvelope(surfaceId, action);
    discoveryRequest.current = envelope.request_id;
    if (action.name === "discovery.refine") imageRequest.current = envelope.request_id;
    setProductActionError(null);
    setIsLoading(true);
    try { websocket.current.send(JSON.stringify(envelope)); return true; }
    catch { imageRequest.current = null; discoveryRequest.current = null; setIsLoading(false); setProductActionError("ส่งรายการไม่สำเร็จ กรุณาลองอีกครั้ง"); return false; }
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

  function sendVideoInquiry(attachmentId: string, query: string): boolean {
    query = query.trim();
    if (!query || query.length > 2000 || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(attachmentId) || !videoUploadToken || websocket.current?.readyState !== WebSocket.OPEN || isLoading || videoRequest.current || imageRequest.current) return false;
    const requestId = crypto.randomUUID();
    videoRequest.current = requestId;
    setProductActionError(null);
    setIsLoading(true);
    try {
      websocket.current.send(JSON.stringify({ type: "knowledge.video.inquire", request_id: requestId, attachment_id: attachmentId, query }));
      return true;
    } catch {
      videoRequest.current = null;
      setIsLoading(false);
      setProductActionError("ส่งคำถามเกี่ยวกับวิดีโอไม่สำเร็จ กรุณาลองใหม่");
      return false;
    }
  }

  function resetHistory() {
    discoveryRequest.current = null;
    videoRequest.current = null;
    setVideoUploadToken(null);
    imageRequest.current = null;
    setImageSearchState({ kind: "idle" });
    setImageComposerEpoch((value) => value + 1);
    setPresentations({});
    setA2uiSurfaces({});
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
    videoUploadToken,
    sendVideoInquiry,
    sendImageSearch,
    sendKnowledgeInquiry,
    sendTextMessage,
    sendProductInquiry,
    presentations,
    a2uiSurfaces,
    sendDiscoveryAction,
    productActionError,
    sendAudioMessage,
    history,
    resetHistory,
    agentName,
    isLoading,
    voiceResponseEnabled,
  };
}
