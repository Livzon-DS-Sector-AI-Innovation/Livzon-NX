/* @vitest-environment happy-dom */

import type { CSSProperties, ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    AlertOutlined: Icon,
    ArrowRightOutlined: Icon,
    CheckCircleOutlined: Icon,
    ClockCircleOutlined: Icon,
    EnvironmentOutlined: Icon,
    RobotOutlined: Icon,
    TeamOutlined: Icon,
    UserOutlined: Icon,
    WarningOutlined: Icon,
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type Props = {
    children?: ReactNode
    style?: CSSProperties
    title?: ReactNode
  }

  const Box = ({ children, style, title }: Props) => createElement('div', { style }, title, children)
  const Text = ({ children, style }: Props) => createElement('span', { style }, children)
  const Title = ({ children, style }: Props) => createElement('h1', { style }, children)

  return {
    Card: Box,
    Col: Box,
    Drawer: Box,
    Row: Box,
    Space: Box,
    Table: Box,
    Tag: Text,
    Typography: { Text, Title },
  }
})

import { antdTheme } from '@/lib/antd-theme'
import SafetyDashboard, { type DashboardData } from './SafetyDashboard'

const dashboardData: DashboardData = {
  openHazardCount: 3,
  unfinishedIdentCount: 1,
  expiringCerts: [],
  todaySpecialOps: [],
  todayDailyRisks: [],
}

describe('SafetyDashboard font contract', () => {
  it('uses the shared UI font variable for the dashboard and Ant Design theme', () => {
    const markup = renderToStaticMarkup(<SafetyDashboard data={dashboardData} />)

    expect(antdTheme.token?.fontFamily).toBe('var(--font-ui)')
    expect(markup).toContain('安全管理总览')
    expect(markup.match(/font-family:\s*var\(--font-ui\)/g)?.length).toBeGreaterThanOrEqual(4)
  })
})
