"use client"

import dynamic from "next/dynamic"
import { MessageOutlined, RobotOutlined } from "@ant-design/icons"
import { Button } from "antd"
import { useAgentStore } from "@/stores/agent"

const LazyAgentFloatingAssistant = dynamic(
  () =>
    import("@/components/agent/AgentFloatingAssistant").then(
      (mod) => mod.AgentFloatingAssistant,
    ),
  {
    ssr: false,
    loading: () => (
      <Button
        aria-label="正在加载中枢助手"
        title="Livzon助手"
        type="primary"
        shape="circle"
        loading
        className="agent-floating-entry-button !fixed !bottom-6 !right-6 !z-50 !h-14 !w-14 !shadow-lg"
      />
    ),
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
    <Button
      aria-label={minimized ? "展开中枢助手" : "打开中枢助手"}
      title="Livzon助手"
      type="primary"
      shape="circle"
      icon={minimized ? <MessageOutlined /> : <RobotOutlined />}
      onClick={() => {
        setOpen(true)
        setMinimized(false)
      }}
      className="agent-floating-entry-button !fixed !bottom-6 !right-6 !z-50 !h-14 !w-14 !shadow-lg"
    />
  )
}
