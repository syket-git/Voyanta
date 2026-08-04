"use client";

import { LogOut, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { UsageMeter } from "@/components/billing/usage-meter";
import { useThreads } from "@/components/chat/threads-provider";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
} from "@/components/ui/sidebar";
import { deleteThread, logout, renameThread } from "@/lib/voyanta";

const SKELETON_WIDTHS = ["82%", "64%", "73%", "55%"];

export function ThreadSidebar({ email }: { email: string }) {
  const { threads, loading, refresh } = useThreads();
  const params = useParams<{ threadId?: string }>();
  const router = useRouter();

  const [renaming, setRenaming] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  async function commitRename(threadId: string) {
    const title = draftTitle.trim();
    setRenaming(null);

    if (!title) return;

    try {
      await renameThread(threadId, title);
      await refresh();
    } catch {
      toast.error("Could not rename that thread.");
    }
  }

  async function confirmDelete() {
    const threadId = pendingDelete;
    setPendingDelete(null);

    if (!threadId) return;

    try {
      await deleteThread(threadId);
      await refresh();
      if (params?.threadId === threadId) router.replace("/chat");
    } catch {
      toast.error("Could not delete that thread.");
    }
  }

  async function signOut() {
    try {
      await logout();
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <>
      <Sidebar collapsible="offcanvas">
        <SidebarHeader className="gap-3 border-b border-sidebar-border p-3">
          <Link
            href="/"
            className="flex items-baseline gap-2 px-1 font-display text-base font-semibold tracking-tight"
          >
            Voyanta
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-sodium" />
          </Link>

          <Button
            render={<Link href="/chat" />}
            nativeButton={false}
            size="sm"
            className="w-full gap-1.5 font-mono text-[0.6875rem] uppercase tracking-[0.12em]"
          >
            <Plus aria-hidden className="size-3.5" />
            New trip
          </Button>
        </SidebarHeader>

        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel className="rule-label">Threads</SidebarGroupLabel>

            <SidebarMenu>
              {loading ? (
                SKELETON_WIDTHS.map((width) => (
                  <SidebarMenuItem key={width}>
                    <SidebarMenuSkeleton width={width} />
                  </SidebarMenuItem>
                ))
              ) : threads.length === 0 ? (
                <p className="px-2 py-1.5 text-xs leading-5 text-muted-foreground">
                  Nothing yet. Your trips will collect here.
                </p>
              ) : (
                threads.map((thread) => (
                  <SidebarMenuItem key={thread.id}>
                    {renaming === thread.id ? (
                      <Input
                        autoFocus
                        value={draftTitle}
                        onChange={(event) => setDraftTitle(event.target.value)}
                        onBlur={() => commitRename(thread.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") commitRename(thread.id);
                          if (event.key === "Escape") setRenaming(null);
                        }}
                        className="h-8 text-sm"
                        aria-label="Thread title"
                      />
                    ) : (
                      <>
                        <SidebarMenuButton
                          render={<Link href={`/chat/${thread.id}`} />}
                          isActive={params?.threadId === thread.id}
                        >
                          <span>{thread.title}</span>
                        </SidebarMenuButton>

                        <DropdownMenu>
                          <DropdownMenuTrigger
                            render={
                              <SidebarMenuAction showOnHover aria-label="Thread actions">
                                <MoreHorizontal aria-hidden />
                              </SidebarMenuAction>
                            }
                          />
                          <DropdownMenuContent side="right" align="start">
                            <DropdownMenuItem
                              onClick={() => {
                                setDraftTitle(thread.title);
                                setRenaming(thread.id);
                              }}
                            >
                              <Pencil aria-hidden className="size-3.5" />
                              Rename
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              variant="destructive"
                              onClick={() => setPendingDelete(thread.id)}
                            >
                              <Trash2 aria-hidden className="size-3.5" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </>
                    )}
                  </SidebarMenuItem>
                ))
              )}
            </SidebarMenu>
          </SidebarGroup>
        </SidebarContent>

        <SidebarFooter className="gap-3 border-t border-sidebar-border p-3">
          <UsageMeter />

          <div className="flex items-center justify-between gap-2 border-t border-sidebar-border pt-3">
            <span className="truncate font-mono text-[0.6875rem] text-muted-foreground">
              {email}
            </span>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={signOut}
              aria-label="Sign out"
            >
              <LogOut aria-hidden className="size-3.5" />
            </Button>
          </div>
        </SidebarFooter>
      </Sidebar>

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this thread?</AlertDialogTitle>
            <AlertDialogDescription>
              The conversation and everything the planner found for it are removed. This
              cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
