interface ComposerProps {
  audioChat?: React.ReactNode;
}

export function Composer({ audioChat }: ComposerProps) {
  return (
    <div className="flex flex-col items-center justify-center px-5 py-8 w-full max-w-2xl">
      {audioChat}
    </div>
  );
}
