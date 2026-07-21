"use client"

import { create } from "zustand"
import type { AgentConfirmation, AgentMessage } from "@/lib/api/agent"

interface AgentState {
  open: boolean
  minimized: boolean
  expanded: boolean
  sessionId: string | null
  messages: AgentMessage[]
  draft: string
  pendingConfirmations: AgentConfirmation[]
  loading: boolean
  error: string | null
  setOpen: (open: boolean) => void
  setMinimized: (minimized: boolean) => void
  setExpanded: (expanded: boolean) => void
  setSessionId: (sessionId: string | null) => void
  setDraft: (draft: string) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  addMessage: (message: AgentMessage) => void
  appendMessageContent: (messageId: string, delta: string) => void
  updateMessage: (messageId: string, message: AgentMessage) => void
  removeMessage: (messageId: string) => void
  setPendingConfirmations: (confirmations: AgentConfirmation[]) => void
  upsertConfirmation: (confirmation: AgentConfirmation) => void
  removeConfirmation: (confirmationId: string) => void
  loadConversation: (input: {
    sessionId: string
    messages: AgentMessage[]
    confirmations: AgentConfirmation[]
  }) => void
  startNewConversation: () => void
}

export const useAgentStore = create<AgentState>((set) => ({
  open: false,
  minimized: false,
  expanded: false,
  sessionId: null,
  messages: [],
  draft: "",
  pendingConfirmations: [],
  loading: false,
  error: null,
  setOpen: (open) =>
    set(open ? { open, minimized: false } : { open, minimized: false, expanded: false }),
  setMinimized: (minimized) =>
    set((state) => ({
      minimized,
      expanded: minimized ? false : state.expanded,
    })),
  setExpanded: (expanded) => set({ expanded, minimized: false }),
  setSessionId: (sessionId) => set({ sessionId }),
  setDraft: (draft) => set({ draft }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  appendMessageContent: (messageId, delta) =>
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === messageId
          ? { ...message, content: `${message.content}${delta}` }
          : message,
      ),
    })),
  updateMessage: (messageId, nextMessage) =>
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === messageId ? nextMessage : message,
      ),
    })),
  removeMessage: (messageId) =>
    set((state) => ({
      messages: state.messages.filter((message) => message.id !== messageId),
    })),
  setPendingConfirmations: (confirmations) => set({
    pendingConfirmations: confirmations.filter(
      (item) => item.status === "pending" && new Date(item.expires_at).getTime() > Date.now(),
    ),
  }),
  upsertConfirmation: (confirmation) =>
    set((state) => {
      if (confirmation.status !== "pending" || new Date(confirmation.expires_at).getTime() <= Date.now()) {
        return {
          pendingConfirmations: state.pendingConfirmations.filter(
            (item) => item.id !== confirmation.id,
          ),
        }
      }
      const exists = state.pendingConfirmations.some((item) => item.id === confirmation.id)
      return {
        pendingConfirmations: exists
          ? state.pendingConfirmations.map((item) =>
              item.id === confirmation.id ? confirmation : item,
            )
          : [...state.pendingConfirmations, confirmation],
      }
    }),
  removeConfirmation: (confirmationId) =>
    set((state) => ({
      pendingConfirmations: state.pendingConfirmations.filter(
        (item) => item.id !== confirmationId,
      ),
    })),
  loadConversation: ({ sessionId, messages, confirmations }) =>
    set({
      sessionId,
      messages,
      pendingConfirmations: confirmations.filter(
        (item) => item.status === "pending" && new Date(item.expires_at).getTime() > Date.now(),
      ),
      draft: "",
      loading: false,
      error: null,
    }),
  startNewConversation: () =>
    set({
      sessionId: null,
      messages: [],
      draft: "",
      pendingConfirmations: [],
      loading: false,
      error: null,
    }),
}))
