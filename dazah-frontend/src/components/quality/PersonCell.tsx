'use client'

import { qualityTokens } from './themeTokens'
import { Avatar } from 'antd'
import { UserOutlined } from '@ant-design/icons'

interface PersonCellProps {
  name?: string | null
  avatarUrl?: string | null
}

function stringToColor(str: string): string {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  const colors = [qualityTokens.primary, '#7b3ff2', qualityTokens.success, qualityTokens.orangeText, '#d46b08', '#cf1322']
  return colors[Math.abs(hash) % colors.length]
}

export function PersonCell({ name, avatarUrl }: PersonCellProps) {
  if (!name || name === '-') {
    return <span style={{ color: '#bbb' }}>-</span>
  }
  const firstName = name.trim().charAt(0)
  const bgColor = stringToColor(name)
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <Avatar
        size={24}
        src={avatarUrl || undefined}
        style={{ backgroundColor: bgColor, flexShrink: 0 }}
        icon={!avatarUrl ? <UserOutlined /> : undefined}
      >
        {firstName}
      </Avatar>
      <span>{name}</span>
    </span>
  )
}
