'use client'

import { Card, Form, Switch } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { useAgentEntryPreferences } from '@/stores/agent-entry-preferences'

export default function AgentEntryVisibilitySettings() {
  const { visible, hydrated, setVisible } = useAgentEntryPreferences()

  return (
    <Card title="助手悬浮入口">
      <Form layout="vertical">
        <Form.Item label="Livzon助手悬浮按钮">
          <Switch
            aria-label="Livzon助手悬浮按钮"
            checked={visible}
            disabled={!hydrated}
            checkedChildren="显示"
            unCheckedChildren="隐藏"
            onChange={setVisible}
          />
        </Form.Item>
      </Form>
      <PlatformNotice
        type="info"
        showIcon
        title="即时生效，仅保存在当前浏览器；可随时在此恢复显示。"
        description="此设置控制 Livzon助手悬浮按钮的显示或隐藏。隐藏后，已展开的对话仍可继续使用，收起或关闭后按钮将隐藏；当前对话内容保留。此设置不会停用 Agent、飞书接入或自动化任务，也不会改变其他浏览器的设置。浏览器禁止本地存储时，设置仅在本次页面会话内生效。"
      />
    </Card>
  )
}
