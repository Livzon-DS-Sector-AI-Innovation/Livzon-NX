import { Button } from "antd"

interface AgentEntryButtonProps {
  minimized?: boolean
  loading?: boolean
  onClick?: () => void
}

export function AgentMark() {
  return (
    <svg viewBox="0 0 32 32" fill="none" focusable="false" aria-hidden="true">
      <path d="m7 18 8-8 10 8-10 6-8-6Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="m15 10 0 14M7 18h18" stroke="currentColor" strokeWidth="1.2" opacity=".65" />
      <circle cx="7" cy="18" r="2" fill="currentColor" />
      <circle cx="15" cy="10" r="2" fill="currentColor" />
      <circle cx="25" cy="18" r="2" fill="currentColor" />
      <circle cx="15" cy="24" r="2" fill="currentColor" />
      <path d="M24 5v5m-2.5-2.5h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function AgentEntryButton({
  minimized = false,
  loading = false,
  onClick,
}: AgentEntryButtonProps) {
  return (
    <Button
      aria-label={loading ? "正在加载中枢助手" : minimized ? "展开中枢助手" : "打开中枢助手"}
      title={minimized ? "继续与 Livzon 助手对话" : "Livzon 智能助手"}
      type="primary"
      loading={loading}
      disabled={loading}
      onClick={onClick}
      className="agent-floating-entry-button"
    >
      <span className="agent-entry-copy">
        <span className="agent-entry-eyebrow">LIVZON <span aria-hidden="true">·</span> AGENT</span>
        <span className="agent-entry-label">{loading ? "正在加载" : minimized ? "继续对话" : "智能助手"}</span>
      </span>
      {!loading && (
        <span className="agent-entry-emblem" aria-hidden="true">
          <AgentMark />
        </span>
      )}
    </Button>
  )
}
