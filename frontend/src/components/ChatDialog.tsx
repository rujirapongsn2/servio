"use client";

import clsx from "clsx";
import { useEffect, useMemo, useRef } from "react";

import ChatLoadingDots from "@/components/ChatLoadingDots";
import { MessageBubble } from "@/components/MessageBubble";
import { Message, ToolCall } from "@/lib/types";

interface ChatDialogProps {
  messages: Message[];
  isLoading: boolean;
  collapsed?: boolean;
}

export function ChatHistory({ messages, isLoading, collapsed = false }: ChatDialogProps) {
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

  return (
    <div
      className={clsx(
        "flex w-full flex-col gap-3 flex-1 overflow-y-auto relative transition-all duration-300",
        messages.length === 0 && "flex-grow-0 basis-[calc(50%-72px-52px)]"
      )}
    >
      <div className="flex flex-col gap-3 relative py-6 px-6 pb-12">
        {displayMessages.map((message, index) => {
          // Check if there is any subsequent message after this one,
          // which means this handoff/function call has completed and the
          // conversation has moved on (no spinner needed).
          const nextMessage = displayMessages[index + 1];
          const hasNextFunctionCall =
            nextMessage != null &&
            (nextMessage.type === "function_call" ||
              nextMessage.type === "function_call_output" ||
              nextMessage.type === "message");

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
        {isLoading && <ChatLoadingDots />}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
