"use client";

import AudioChat from "@/components/AudioChat";
import { ChatHistory } from "@/components/ChatDialog";
import { Composer } from "@/components/Composer";
import { Header } from "@/components/Header";
import { useAudio } from "@/hooks/useAudio";
import { useWebsocket } from "@/hooks/useWebsocket";

import "./styles.css";

export default function Home() {
  const {
    isReady: audioIsReady,
    playAudio,
    startRecording,
    stopRecording,
    stopPlaying,
    frequencies,
    playbackFrequencies,
  } = useAudio();
  const {
    isReady: websocketReady,
    sendAudioMessage,
    history: messages,
    resetHistory,
    isLoading,
    agentName,
  } = useWebsocket({
    onNewAudio: playAudio,
  });

  async function handleStopPlaying() {
    await stopPlaying();
  }

  return (
    <div className="w-full h-dvh flex flex-col items-center">
      <Header
        agentName={agentName ?? "Voice Agent"}
        playbackFrequencies={playbackFrequencies}
        stopPlaying={handleStopPlaying}
        resetConversation={resetHistory}
      />
      <ChatHistory messages={messages} isLoading={isLoading} />
      <Composer
        audioChat={
          <AudioChat
            frequencies={frequencies}
            isReady={websocketReady && audioIsReady}
            startRecording={startRecording}
            stopRecording={stopRecording}
            sendAudioMessage={sendAudioMessage}
          />
        }
      />
    </div>
  );
}
