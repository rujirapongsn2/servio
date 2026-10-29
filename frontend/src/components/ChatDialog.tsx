"use client";

import clsx from "clsx";
import { Fragment, useEffect, useMemo, useRef } from "react";

import ChatLoadingDots from "@/components/ChatLoadingDots";
import { MessageBubble } from "@/components/MessageBubble";
import { KnowledgeVideos } from "@/components/KnowledgeVideos";
import { KnowledgeAudio } from "@/components/KnowledgeAudio";
import { KnowledgeImages } from "@/components/KnowledgeImages";
import { ProductCarousel } from "@/components/ProductCarousel";
import { ProductPresentations, type KnowledgeVideo } from "@/lib/product-presentations";
import { answerLandedAfter } from "@/lib/chat-flow";
import { Message, ToolCall } from "@/lib/types";

interface ChatDialogProps {
  messages: Message[];
  locale?: "th" | "en";
  isLoading: boolean;
  collapsed?: boolean;
  presentations?: ProductPresentations;
  onProductInquiry?: (callId: string, productId: string) => void;
  onKnowledgeInquiry?: (messageId: string, cardId: string) => void;
  productActionsDisabled?: boolean;
  productActionError?: string | null;
  /** Hide internal system events (tool calls, agent transfers) — customer surfaces. */
  showSystemEvents?: boolean;
}

export function ChatHistory({ locale = "th", messages, isLoading, collapsed = false, presentations = {}, onProductInquiry, onKnowledgeInquiry, productActionsDisabled = false, productActionError, showSystemEvents = true }: ChatDialogProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Scrolls the dummy element into view when messages change.
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const mergedMessages = useMemo(() => {
    return messages.reduce((newMessages, currentMessage) => {
      newMessages.push(currentMessage);
      if (currentMessage.type === "function_call_output") {
        const callId = currentMessage.call_id;
        const functionCallIndex = newMessages.findIndex(
          (message) =>
            message.type === "function_call" && message.call_id === callId
        );
        if (functionCallIndex !== -1) {
          newMessages[functionCallIndex] = {
            ...newMessages[functionCallIndex],
            output: currentMessage.output,
          } as ToolCall;
        }
      }
      return newMessages;
    }, [] as Message[]);
  }, [messages]);

  const displayMessages = collapsed ? [] : mergedMessages;
  const audioAfterMessage = new Map<number, string[]>();
  let audioCallIds: string[] = [];
  const videoAfterMessage = new Map<number, KnowledgeVideo[]>();
  let turnVideos: KnowledgeVideo[] = [];
  let answerIndex = -1;
  const finishAudioTurn = (endIndex: number, pending: boolean) => {
    const targetIndex = answerIndex >= 0 ? answerIndex : pending ? -1 : endIndex;
    if (audioCallIds.length > 0 && targetIndex >= 0) {
      audioAfterMessage.set(targetIndex, audioCallIds);
    }
    if (turnVideos.length > 0 && targetIndex >= 0) {
      videoAfterMessage.set(targetIndex, Array.from(new Map(turnVideos.map(video => [video.asset_id, video])).values()));
    }
    turnVideos = [];
    audioCallIds = [];
    answerIndex = -1;
  };
  displayMessages.forEach((message, index) => {
    if (message.type === "message" && message.role === "user") {
      finishAudioTurn(index - 1, false);
    }
    if (message.type === "function_call_output") {
      const presentation = presentations[message.call_id];
      if (presentation?.type === "knowledge_video") { turnVideos.push(...presentation.videos); answerIndex = -1; }
      if (presentation?.type === "knowledge_media" && presentation.audio.length > 0) {
        audioCallIds.push(message.call_id);
        answerIndex = -1;
      }
    }
    if (message.type === "message" && message.role === "assistant") {
      if ("id" in message && typeof message.id === "string") {
        const presentation = presentations[message.id];
        if (presentation?.type === "knowledge_video") turnVideos.push(...presentation.videos);
      }
      const content = message.content;
      const hasText = typeof content === "string"
        ? content.trim().length > 0
        : content.some((part) => part.type === "output_text" && part.text.trim().length > 0);
      if (hasText) answerIndex = index;
    }
  });
  finishAudioTurn(displayMessages.length - 1, isLoading);
  let productResponse = false;

  return (
    <div
      data-chat-history
      className={clsx(
        "flex w-full min-w-0 flex-col gap-3 flex-1 overflow-y-auto relative transition-all duration-300",
        messages.length === 0 && "flex-grow-0 basis-[calc(50%-72px-52px)]"
      )}
    >
      <div className="flex min-w-0 flex-col gap-3 relative py-6 px-6 pb-12">
        {displayMessages.map((message, index) => {
          if (message.type === "message" && message.role === "user") productResponse = false;
          if (message.type === "message" && message.role === "assistant" && "id" in message && typeof message.id === "string") {
            const presentation = presentations[message.id];

            if (presentation?.type === "knowledge_product_carousel") {
              const messageId = message.id;
              return <ProductCarousel key={messageId} presentation={presentation} disabled={productActionsDisabled || isLoading || !onKnowledgeInquiry} onInquire={(cardId) => onKnowledgeInquiry?.(messageId, cardId)} />;
            }
          }
          if (message.type === "function_call_output" && presentations[message.call_id]) {
            const presentation = presentations[message.call_id];
            if (presentation.type === "knowledge_video") return null;
            if (presentation.type === "knowledge_media") return <KnowledgeImages key={`images-${message.call_id}`} images={presentation.images} />;
            if (presentation.type === "knowledge_images") return <KnowledgeImages key={`images-${message.call_id}`} images={presentation.images} />;
            if (presentation.type === "knowledge_product_carousel") return null;
            productResponse = true;
            return <ProductCarousel key={`products-${message.call_id}`} presentation={presentation} disabled={productActionsDisabled || isLoading || !onProductInquiry} onInquire={(productId) => onProductInquiry?.(message.call_id, productId)} />;
          }
          if (message.type === "function_call" && !showSystemEvents) {
            // Show tool/transfer lines only while the turn is still working;
            // once the assistant's answer for this turn arrives, hide them.
            if (answerLandedAfter(displayMessages, index)) return null;
          }
          if (message.type === "function_call" && presentations[message.call_id]) return null;
          // Check if there is any subsequent message after this one,
          // which means this handoff/function call has completed and the
          // conversation has moved on (no spinner needed).
          const nextMessage = displayMessages[index + 1];
          const hasNextFunctionCall =
            nextMessage != null &&
            (nextMessage.type === "function_call" ||
              nextMessage.type === "function_call_output" ||
              nextMessage.type === "message");

          if (productResponse && message.type === "message" && message.role === "assistant") {
            return <details key={`answer-${index}`} className="rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-700">
              <summary className="cursor-pointer text-sm text-gray-500">คำตอบเพิ่มเติม</summary>
              <div className="mt-3"><MessageBubble message={message} collapsed={collapsed} /></div>
            </details>;
          }

          return (
            <MessageBubble
              key={
                Object.hasOwn(message, "id")
                  ? // @ts-expect-error - id is not always present
                    message.id
                  : JSON.stringify(message)
              }
              message={message}
              isLast={index === displayMessages.length - 1}
              isLoading={isLoading}
              hasNextFunctionCall={hasNextFunctionCall}
              collapsed={collapsed}
            />
          );
        }).map((messageNode, index) => (
          <Fragment key={index}>
            {messageNode}
            {videoAfterMessage.has(index) && <KnowledgeVideos videos={videoAfterMessage.get(index) ?? []} locale={locale} />}
            {audioAfterMessage.get(index)?.map((callId) => {
              const presentation = presentations[callId];
              return presentation?.type === "knowledge_media"
                ? <KnowledgeAudio key={`audio-${callId}`} audio={presentation.audio} />
                : null;
            })}
          </Fragment>
        ))}
        {productActionError && <p role="alert" className="text-sm text-red-600">{productActionError}</p>}
        {isLoading && <ChatLoadingDots />}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
