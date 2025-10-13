import React from "react";
import { motion } from "motion/react";

import ShuffleIcon from "@/components/icons/ShuffleIcon";
import { ToolCall } from "@/lib/types";

type HandoffMessageProps = {
  message: ToolCall;
  isLast?: boolean;
  isLoading?: boolean;
};

export function HandoffMessage({ message, isLast = false, isLoading = false }: HandoffMessageProps) {
  let agentName: string;
  if (message?.output) {
    agentName = message?.output?.match(/'assistant':\s*'([^']+)'/)?.[1] || "";
  } else {
    agentName = message.name;
  }

  // Always show spinner after transfer message is completed
  const showSpinner = message.status === "completed";

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
                  <div className="flex items-center ml-1">
                    <motion.span
                      className="w-1.5 h-1.5 bg-blue-500 rounded-full"
                      animate={{ opacity: [0.2, 1, 0.2] }}
                      transition={{ duration: 1, repeat: Infinity, ease: "easeInOut" }}
                    />
                    <motion.span
                      className="w-1.5 h-1.5 bg-blue-500 rounded-full mx-0.5"
                      animate={{ opacity: [0.2, 1, 0.2] }}
                      transition={{
                        duration: 1,
                        repeat: Infinity,
                        ease: "easeInOut",
                        delay: 0.2,
                      }}
                    />
                    <motion.span
                      className="w-1.5 h-1.5 bg-blue-500 rounded-full"
                      animate={{ opacity: [0.2, 1, 0.2] }}
                      transition={{
                        duration: 1,
                        repeat: Infinity,
                        ease: "easeInOut",
                        delay: 0.4,
                      }}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
