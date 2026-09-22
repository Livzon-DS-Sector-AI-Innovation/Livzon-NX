"use client"

import dynamic from "next/dynamic"
import { AgentEntryButton } from "@/components/agent/AgentEntryButton"
import { useAgentStore } from "@/stores/agent"

const LazyAgentFloatingAssistant = dynamic(
  () =>
    import("@/components/agent/AgentFloatingAssistant").then(
      (mod) => mod.AgentFloatingAssistant,
    ),
  {
    ssr: false,
    loading: () => <AgentEntryButton loading />,
  },
)

export function AgentFloatingEntry() {
  const open = useAgentStore((state) => state.open)
  const minimized = useAgentStore((state) => state.minimized)
  const setOpen = useAgentStore((state) => state.setOpen)
  const setMinimized = useAgentStore((state) => state.setMinimized)

  if (open) {
    return <LazyAgentFloatingAssistant />
  }

  return (
    <AgentEntryButton
      minimized={minimized}
      onClick={() => {
        setOpen(true)
        setMinimized(false)
      }}
    />
  )
}
