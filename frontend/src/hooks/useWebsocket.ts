import { useEffect, useRef, useState } from "react";

import { parseProductPresentations, ProductPresentations } from "@/lib/product-presentations";
import { Message } from "@/lib/types";
import { arrayBufferToBase64, base64ToArrayBuffer } from "@/lib/utils";
import { getWebsocketBaseUrl } from "@/lib/api";

export function useWebsocket({
  url,
  apiKey,
  onNewAudio,
  onAudioDone,
}: {
  url?: string;
  apiKey?: string;
  onNewAudio?: (audio: Int16Array<ArrayBuffer>) => void;
  onAudioDone?: () => void;
} = {}) {
  const defaultWs = getWebsocketBaseUrl();

  // Add API key to URL if provided
  let wsUrl = url ?? defaultWs;
  if (apiKey) {
    const separator = wsUrl.includes('?') ? '&' : '?';
    wsUrl = `${wsUrl}${separator}api_key=${encodeURIComponent(apiKey)}`;
  }

  url = wsUrl;
  const [isReady, setIsReady] = useState(false);
  const [history, setHistory] = useState<Message[]>([]);
  const [presentations, setPresentations] = useState<ProductPresentations>({});
  const [productActionError, setProductActionError] = useState<string | null>(null);
  const [agentName, setAgentName] = useState<string | null>(null);
  const websocket = useRef<WebSocket | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [voiceResponseEnabled, setVoiceResponseEnabled] = useState(true);

  useEffect(() => {
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
    });
    ws.addEventListener("close", () => {
      if (websocket.current !== ws) return;
      setIsReady(false);
      setIsLoading(false); // Stop loading on close
    });
    ws.addEventListener("error", (event) => {
      if (websocket.current !== ws) return;
      setIsReady(false);
      setIsLoading(false);
      console.error("Websocket error", event);
    });
    ws.addEventListener("message", (event) => {
      if (websocket.current !== ws) return;
      const data = JSON.parse(event.data);
      if (data.type === "product.action.error") {
        setProductActionError(typeof data.message === "string" ? data.message : "ไม่สามารถสอบถามสินค้านี้ได้");
        setIsLoading(false);
        return;
      }
      if (data.type === "error") {
        console.error("WebSocket Error:", data.message);
        alert(data.message); // Alert the user
        setIsLoading(false);
        return;
      }

      // Handle session config from server
      if (data.type === "session.config") {
        if (typeof data.voice_response_enabled === "boolean") {
          setVoiceResponseEnabled(data.voice_response_enabled);
        }
        return;
      }

      if (data.type === "history.updated") {
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
  }, [url, onNewAudio, onAudioDone]);

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

  function resetHistory() {
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
