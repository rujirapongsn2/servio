interface ComposerProps {
  audioChat?: React.ReactNode;
}

export function Composer({ audioChat }: ComposerProps) {
  return (
    <div className="flex flex-col items-center justify-center w-full">
      {audioChat}
    </div>
  );
}
