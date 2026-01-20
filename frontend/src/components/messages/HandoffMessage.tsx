import React from "react";

import ShuffleIcon from "@/components/icons/ShuffleIcon";
import { ToolCall } from "@/lib/types";

type HandoffMessageProps = {
  message: ToolCall;
  isLast?: boolean;
  isLoading?: boolean;
  hasNextFunctionCall?: boolean;
};

export function HandoffMessage({
  message,
  isLast = false,
  isLoading = false,
  hasNextFunctionCall = false
}: HandoffMessageProps) {
  let agentName: string;
  if (message?.output) {
    agentName = message?.output?.match(/'assistant':\s*'([^']+)'/)?.[1] || "";
  } else {
    agentName = message.name;
  }

  // Show spinner if transfer completed and no function call yet
  const showSpinner = message.status === "completed" && !hasNextFunctionCall;

  return (
    <div className="flex flex-col w-[70%] relative mb-[-8px]">
      <div>
        <div className="flex flex-col text-sm rounded-[16px]">
          <div className="font-semibold p-3 pl-0 text-gray-700 rounded-b-none flex gap-2">
            <div className="flex gap-2 items-center text-blue-500 ml-[-8px]">
              <ShuffleIcon width={16} height={16} />
              <div className="text-sm font-medium flex items-center gap-2">
                {message.status === "completed"
                  ? `Transferred to ${agentName}`
                  : `Transferring conversation...`}
                {showSpinner && (
                  <div className="flex items-center ml-2 gap-1">
                    <span
                      className="w-1.5 h-1.5 bg-blue-500 rounded-full"
                      style={{
                        animation: 'pulse 1.4s ease-in-out infinite'
                      }}
                    />
                    <span
                      className="w-1.5 h-1.5 bg-blue-500 rounded-full"
                      style={{
                        animation: 'pulse 1.4s ease-in-out 0.2s infinite'
                      }}
                    />
                    <span
                      className="w-1.5 h-1.5 bg-blue-500 rounded-full"
                      style={{
                        animation: 'pulse 1.4s ease-in-out 0.4s infinite'
                      }}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
      <style jsx>{`
        @keyframes pulse {
          0%, 100% {
            opacity: 0.2;
          }
          50% {
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}
