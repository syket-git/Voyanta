import type { Metadata } from "next";

import { ChatPanel } from "@/components/chat/chat-panel";

export const metadata: Metadata = {
  title: "Plan a trip — Voyanta",
  description: "Plan a day-by-day itinerary with live flight data and cited sources.",
};

export default function ChatPage() {
  return <ChatPanel />;
}
