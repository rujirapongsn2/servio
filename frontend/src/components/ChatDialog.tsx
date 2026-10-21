"use client";

import clsx from "clsx";
import { useEffect, useMemo, useRef } from "react";

import ChatLoadingDots from "@/components/ChatLoadingDots";
import { MessageBubble } from "@/components/MessageBubble";
import { ProductCarousel } from "@/components/ProductCarousel";
import { ProductPresentations } from "@/lib/product-presentations";
import { Message, ToolCall } from "@/lib/types";

interface ChatDialogProps {
  messages: Message[];
  isLoading: boolean;
  collapsed?: boolean;
  presentations?: ProductPresentations;
  onProductInquiry?: (callId: string, productId: string) => void;
  productActionsDisabled?: boolean;
  productActionError?: string | null;
}

export function ChatHistory({ messages, isLoading, collapsed = false, presentations = {}, onProductInquiry, productActionsDisabled = false, productActionError }: ChatDialogProps) {
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
  let productResponse = false;

  return (
    <div
      className={clsx(
        "flex w-full min-w-0 flex-col gap-3 flex-1 overflow-y-auto relative transition-all duration-300",
        messages.length === 0 && "flex-grow-0 basis-[calc(50%-72px-52px)]"
      )}
    >
      <div className="flex min-w-0 flex-col gap-3 relative py-6 px-6 pb-12">
        {displayMessages.map((message, index) => {
          if (message.type === "message" && message.role === "user") productResponse = false;
          if (message.type === "function_call_output" && presentations[message.call_id]) {
            productResponse = true;
            return <ProductCarousel key={`products-${message.call_id}`} presentation={presentations[message.call_id]} disabled={productActionsDisabled || isLoading || !onProductInquiry} onInquire={(productId) => onProductInquiry?.(message.call_id, productId)} />;
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
        })}
        {productActionError && <p role="alert" className="text-sm text-red-600">{productActionError}</p>}
        {isLoading && <ChatLoadingDots />}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
