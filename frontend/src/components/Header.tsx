"use client";

import clsx from "clsx";
import { AnimatePresence, motion } from "motion/react";
import Image from "next/image";

import { AudioPlayback } from "@/components/AudioPlayback";
import PauseIcon from "@/components/icons/PauseIcon";
import WriteIcon from "@/components/icons/WriteIcon";
import { Button } from "@/components/ui/Button";

export function Header({
  agentName,
  playbackFrequencies,
  stopPlaying,
  resetConversation,
  collapsed,
  onToggleCollapsed,
}: {
  agentName: string;
  playbackFrequencies: number[];
  stopPlaying: () => Promise<void>;
  resetConversation: () => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  const showAudioPlayback = playbackFrequencies.length === 5;

  return (
    <div className="flex flex-row gap-2 w-full relative justify-between items-center py-5 px-6 bg-white text-gray-900 border-b border-gray-200 shadow-sm dark:bg-gray-900 dark:text-white dark:border-gray-800 min-h-24">
      <div className="flex flex-row gap-5 items-center">
        <Image src="/servio_logo.png" alt="Servio Logo" width={80} height={80} className="rounded-lg" />
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Voice Agent</h1>
      </div>
      {agentName && (
        <div
          className={clsx(
            "flex text-sm font-semibold border border-gray-200 rounded-xl py-3 px-2 items-center overflow-hidden dark:border-gray-700 bg-white dark:bg-gray-800 dark:text-white shadow-sm"
          )}
        >
          <div className="ml-6 mr-4">
            <AnimatePresence initial={false}>
              {showAudioPlayback && (
                <motion.div
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: "auto" }}
                  exit={{ opacity: 0, width: 0 }}
                  transition={{
                    type: "spring",
                    stiffness: 200,
                    damping: 8,
                    mass: 0.5,
                  }}
                  style={{ originX: 0 }}
                  className="flex items-center overflow-hidden"
                >
                  <AudioPlayback
                    playbackFrequencies={playbackFrequencies}
                    itemClassName="bg-black"
                    height={24}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          <motion.div
            layout="size"
            initial={{ width: 0 }}
            animate={{ width: "auto" }}
            transition={{
              type: "spring",
              stiffness: 200,
              damping: 8,
              mass: 0.5,
            }}
            style={{ originX: 0.5 }}
            className="overflow-hidden whitespace-nowrap text-center"
          >
            <AnimatePresence mode="wait">
              <motion.span
                key={agentName}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
              >
                {agentName}
              </motion.span>
            </AnimatePresence>
          </motion.div>
          <div className="mr-6 ml-4">
            <AnimatePresence initial={false}>
              {showAudioPlayback && (
                <motion.div
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: "auto" }}
                  exit={{ opacity: 0, width: 0 }}
                  transition={{
                    type: "spring",
                    stiffness: 200,
                    damping: 8,
                    mass: 0.5,
                  }}
                  style={{ originX: 1 }}
                  className="flex items-center overflow-hidden -pr-2"
                >
                  <Button
                    variant="primary"
                    size="iconTiny"
                    onClick={stopPlaying}
                  >
                    <PauseIcon />
                  </Button>
                  {/* <PauseButton stopPlaying={stopPlaying} isPlaying /> */}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      )}
      <div className="flex flex-row gap-3 items-center">
        <Button
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Expand messages" : "Collapse messages"}
          title={collapsed ? "แสดงบทสนทนา (Expand)" : "ซ่อนบทสนทนา (Collapse)"}
          size="sm"
          variant="outline"
          className="text-gray-700 dark:text-gray-300"
        >
          {collapsed ? "Expand" : "Collapse"}
        </Button>
        <Button
          onClick={resetConversation}
          aria-label="Start new conversation"
          size="iconSmall"
          variant="primary"
        >
          <WriteIcon width={20} height={20} />
        </Button>
      </div>
    </div>
  );
}
