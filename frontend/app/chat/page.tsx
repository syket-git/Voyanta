import type { Metadata } from "next";

import { ChatWorkspace } from "@/components/chat/chat-workspace";

export const metadata: Metadata = {
  title: "Plan a trip — Voyanta",
  description: "Plan a day-by-day itinerary with live flight data and cited sources.",
};

export default function NewChatPage() {
  return <ChatWorkspace threadId={null} />;
}
