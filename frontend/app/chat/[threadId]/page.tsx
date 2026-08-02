import type { Metadata } from "next";

import { ChatWorkspace } from "@/components/chat/chat-workspace";

export const metadata: Metadata = {
  title: "Plan a trip — Voyanta",
};

export default async function ThreadPage({
  params,
}: PageProps<"/chat/[threadId]">) {
  const { threadId } = await params;

  // Keyed so switching threads mounts a fresh workspace rather than resetting state
  // through an effect.
  return <ChatWorkspace key={threadId} threadId={threadId} />;
}
