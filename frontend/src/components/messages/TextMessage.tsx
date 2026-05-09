import clsx from "clsx";
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { normalizeMarkdownForChat } from "@/lib/markdown";

type CustomLinkProps = {
  href?: string;
  children?: React.ReactNode;
};

const CustomLink = ({ href, children, ...props }: CustomLinkProps) => (
  <a
    href={href}
    {...props}
    className="text-blue-600 hover:text-blue-700 underline underline-offset-2 font-medium dark:text-blue-400 dark:hover:text-blue-300"
  >
    {children}
  </a>
);

type TextMessageProps = {
  text: string;
  isUser: boolean;
  collapsed?: boolean;
};

export function TextMessage({ text, isUser, collapsed = false }: TextMessageProps) {
  const displayText = isUser ? text : normalizeMarkdownForChat(text);

  return (
    <div
      className={clsx("flex flex-row gap-3", {
        "justify-end": isUser,
      })}
    >
      <div
        className={clsx("rounded-2xl py-3 px-4 shadow-sm overflow-hidden", {
          "max-w-[85%] text-white bg-blue-600 dark:bg-blue-600": isUser,
          "max-w-[95%] text-gray-900 bg-gray-100 dark:bg-gray-700 dark:text-gray-100": !isUser,
        })}
      >
        <div className={clsx("text-[15px] leading-relaxed markdown-content", { "clamp-1": collapsed })}>
          <ReactMarkdown
            components={{ a: CustomLink }}
            remarkPlugins={[remarkGfm]}
          >
            {displayText}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
