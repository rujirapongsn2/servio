import type { Message } from "@/lib/types";

/**
 * True when an assistant answer exists after `index` — the turn that owns
 * the system event at `index` has finished and its tool/transfer rows can
 * be hidden on customer surfaces (they stay visible while the turn works).
 */
export function answerLandedAfter(messages: Message[], index: number): boolean {
  for (let i = index + 1; i < messages.length; i += 1) {
    const later = messages[i];
    if (later.type !== "message" || later.role !== "assistant") continue;
    if (typeof later.content === "string") {
      if (later.content.trim().length > 0) return true;
    } else if (later.content.some((part) => part.type === "output_text" && part.text.trim().length > 0)) {
      return true;
    }
  }
  return false;
}
