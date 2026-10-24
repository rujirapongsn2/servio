"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { KnowledgeAudio } from "@/components/KnowledgeAudio";
import { KnowledgeImages } from "@/components/KnowledgeImages";
import { ProductCarousel } from "@/components/ProductCarousel";
import { normalizeMarkdownForChat } from "@/lib/markdown";
import type { ProductPresentations } from "@/lib/product-presentations";

export default function AgentTestContent({ content, presentations = {} }: {
  content: string;
  presentations?: ProductPresentations;
}) {
  const images = Array.from(new Map(Object.values(presentations).flatMap(presentation =>
    presentation.type === "knowledge_images" || presentation.type === "knowledge_media"
      ? presentation.images.map(image => [image.asset_id, image] as const)
      : []
  )).values());
  return <div className="min-w-0 space-y-3">
    <div className="markdown-content break-words text-sm">
      <ReactMarkdown remarkPlugins={[remarkGfm]} disallowedElements={["img"]}>
        {normalizeMarkdownForChat(content)}
      </ReactMarkdown>
    </div>
    <KnowledgeImages images={images} />
    {Object.entries(presentations).map(([callId, presentation]) => {
      switch (presentation.type) {
        case "knowledge_images":
          return null;
        case "knowledge_media":
          return <KnowledgeAudio key={callId} audio={presentation.audio} />;
        case "product_carousel":
        case "knowledge_product_carousel":
          return <ProductCarousel key={callId} presentation={presentation} disabled onInquire={() => {}} />;
        default: {
          const exhaustive: never = presentation;
          return exhaustive;
        }
      }
    })}
  </div>;
}
