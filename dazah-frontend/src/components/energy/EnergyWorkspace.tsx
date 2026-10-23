'use client'

import { useSyncExternalStore } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { Button, Menu, Typography } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { ledgerRequest, type Options } from '@/lib/api/energy-ledger'
import { useAuthStore } from '@/stores/auth'
import { EnergyEntryClient } from './EnergyEntryClient'
import { EnergyDashboard } from './EnergyDashboard'
import { EnergyReportsClient } from './EnergyReportsClient'
import { EnergySettingsClient } from './EnergySettingsClient'
import styles from './EnergyWorkspace.module.css'

export type EnergyMode = 'overview' | 'entry' | 'reports' | 'analysis' | 'data-quality' | 'settings'
const PAGES: { mode: EnergyMode; label: string; href: string }[] = [
  { mode: 'overview', label: '能源仪表盘', href: '/energy' },
  { mode: 'entry', label: '原始数据填写', href: '/energy/entry' },
  { mode: 'reports', label: '能源台账', href: '/energy/reports' },
  { mode: 'analysis', label: '用量分析', href: '/energy/analysis' },
  { mode: 'data-quality', label: '数据质量', href: '/energy/data-quality' },
  { mode: 'settings', label: '配置管理', href: '/energy/settings' },
]
const subscribeToHydration = () => () => {}

export function EnergyWorkspace({ mode }: { mode: EnergyMode }) {
  const params = useSearchParams()
  const canQuery = useAuthStore(state => state.hasPagePermission('energy:reports', 'query'))
  const canEnter = useAuthStore(state => state.hasPagePermission('energy:entry', 'query'))
  const hydrated = useSyncExternalStore(subscribeToHydration, () => true, () => false)
  const isLedger = mode === 'entry' || mode === 'reports'
  const options = useQuery({ queryKey: ['energy-ledger', 'options'], queryFn: () => ledgerRequest<Options>('/ledger-options') })
  return <main className={styles.workspace}>
    <Typography.Title level={3}>{PAGES.find(page => page.mode === mode)?.label}</Typography.Title>
    {options.error && <PlatformNotice type="error" title={options.error.message} action={<Button onClick={() => void options.refetch()}>重试</Button>} />}
    {isLedger && <nav className={styles.ledgerNavigation} aria-label="能源台账操作">
      <Menu mode="horizontal" selectedKeys={[mode]} items={[
        ...(mode === 'reports' || (hydrated && canQuery) ? [{ key: 'reports', label: <Link href={mode === 'reports' ? `/energy/reports${params.size ? `?${params}` : ''}` : '/energy/reports'} aria-current={mode === 'reports' ? 'page' : undefined}>台账查询</Link> }] : []),
        ...(mode === 'entry' || (hydrated && canEnter) ? [{ key: 'entry', label: <Link href={mode === 'entry' ? `/energy/entry${params.size ? `?${params}` : ''}` : '/energy/entry'} aria-current={mode === 'entry' ? 'page' : undefined}>原始数据填写</Link> }] : []),
      ]} />
    </nav>}
    {mode === 'overview' ? <EnergyDashboard key={params.toString()} />
      : mode === 'entry' ? <EnergyEntryClient />
      : mode === 'settings' ? <EnergySettingsClient options={options.data} />
        : <EnergyReportsClient key={`${mode}:${params}`} mode={mode} />}
  </main>
}
