import { redirect } from "next/navigation";

import { ThreadSidebar } from "@/components/chat/thread-sidebar";
import { ThreadsProvider } from "@/components/chat/threads-provider";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { getUser } from "@/lib/session";

export default async function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // proxy.ts only checks that a cookie is present. This verifies it against the backend,
  // so an expired or revoked session cannot render the app shell.
  const user = await getUser();

  if (!user) redirect("/login");

  return (
    <ThreadsProvider>
      <SidebarProvider>
        <ThreadSidebar email={user.email} />
        <SidebarInset>{children}</SidebarInset>
      </SidebarProvider>
    </ThreadsProvider>
  );
}
