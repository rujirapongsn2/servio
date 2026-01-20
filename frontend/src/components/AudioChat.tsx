import React, { useState } from "react";

import { AudioPlayback } from "@/components/AudioPlayback";
import PhoneIcon from "@/components/icons/PhoneIcon";
import PhoneOffIcon from "@/components/icons/PhoneOffIcon";
import MicIcon from "@/components/icons/MicIcon";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/utils";

interface AudioChatProps {
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<Int16Array<ArrayBuffer>>;
  sendAudioMessage: (audio: Int16Array<ArrayBuffer>) => void;
  isReady: boolean;
  frequencies: number[];
}

const AudioChat = ({
  isReady = true,
  startRecording,
  stopRecording,
  sendAudioMessage,
  frequencies,
}: AudioChatProps) => {
  const [isInCall, setIsInCall] = useState(false);
  const [isPushingToTalk, setIsPushingToTalk] = useState(false);

  async function handleStartCall() {
    setIsInCall(true);
    console.log('📞 Call started - Ready for Push-to-Talk');
  }

  async function handleEndCall() {
    // If currently recording, stop it first
    if (isPushingToTalk) {
      await handlePushToTalkEnd();
    }
    setIsInCall(false);
    console.log('📞 Call ended');
  }

  async function handlePushToTalkStart() {
    if (!isInCall) return;

    setIsPushingToTalk(true);
    console.log('🎤 Push-to-Talk: Recording started');
    await startRecording();
  }

  async function handlePushToTalkEnd() {
    if (!isPushingToTalk) return;

    console.log('🛑 Push-to-Talk: Recording stopped');
    setIsPushingToTalk(false);

    const audio = await stopRecording();
    if (audio.length > 0) {
      console.log('📤 Sending audio, length:', audio.length);
      sendAudioMessage(audio);
    } else {
      console.log('⚠️ No audio to send');
    }
  }

  if (!isInCall) {
    // Show Call button
    return (
      <div className="flex flex-col items-center gap-4 w-full">
        <Button
          variant="primary"
          size="icon"
          disabled={!isReady}
          aria-label="Start Call"
          className="w-20 h-20 rounded-full bg-green-500 hover:bg-green-600 dark:bg-green-600 dark:hover:bg-green-700 transition-all duration-300"
          onClick={handleStartCall}
        >
          <PhoneIcon className="w-10 h-10" />
        </Button>
        <p className="text-center text-sm text-gray-500 dark:text-gray-400">
          Press to call
        </p>
      </div>
    );
  }

  // In call - show Push-to-Talk interface
  return (
    <div className="flex flex-col items-center gap-4 w-full max-w-md">
      {/* Push-to-Talk Button */}
      <div className="relative flex flex-col items-center gap-3">
        <Button
          variant="primary"
          size="icon"
          disabled={!isReady}
          aria-label={isPushingToTalk ? "Recording..." : "Hold to speak"}
          className={cn(
            "w-32 h-32 rounded-full transition-all duration-200",
            isPushingToTalk
              ? "bg-red-500 hover:bg-red-600 dark:bg-red-600 scale-110 shadow-lg shadow-red-500/50"
              : "bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700"
          )}
          onMouseDown={handlePushToTalkStart}
          onMouseUp={handlePushToTalkEnd}
          onMouseLeave={handlePushToTalkEnd}
          onTouchStart={(e) => {
            e.preventDefault();
            handlePushToTalkStart();
          }}
          onTouchEnd={(e) => {
            e.preventDefault();
            handlePushToTalkEnd();
          }}
        >
          <MicIcon className="w-16 h-16" />
        </Button>

        {/* Status Text */}
        <p className={cn(
          "text-center font-medium transition-colors",
          isPushingToTalk
            ? "text-red-500 dark:text-red-400 text-base"
            : "text-gray-600 dark:text-gray-400 text-sm"
        )}>
          {isPushingToTalk ? "🔴 Recording..." : "Press and hold to speak"}
        </p>
      </div>

      {/* Audio Visualization */}
      {isPushingToTalk && (
        <div className="w-full">
          <AudioPlayback
            playbackFrequencies={frequencies}
            itemClassName="bg-red-500 w-[4px] sm:w-[6px]"
            className="gap-[3px] w-full"
            height={48}
          />
        </div>
      )}

      {/* End Call Button */}
      <Button
        variant="stop"
        size="default"
        aria-label="End Call"
        className="mt-4 bg-red-500 hover:bg-red-600 dark:bg-red-600 dark:hover:bg-red-700"
        onClick={handleEndCall}
      >
        <PhoneOffIcon className="w-5 h-5 mr-2" />
        End Call
      </Button>
    </div>
  );
};

export default AudioChat;
