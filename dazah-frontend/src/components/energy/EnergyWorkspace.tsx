'use client'

import { useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Typography } from 'antd'
import { ledgerRequest, type Options } from '@/lib/api/energy-ledger'
import { EnergyEntryClient } from './EnergyEntryClient'
import { EnergyReportsClient } from './EnergyReportsClient'
import { EnergySettingsClient } from './EnergySettingsClient'
import styles from './EnergyWorkspace.module.css'

export type EnergyMode = 'overview' | 'entry' | 'reports' | 'analysis' | 'data-quality' | 'settings'
const PAGES: { mode: EnergyMode; label: string; href: string }[] = [
  { mode: 'overview', label: '能源总览', href: '/energy' },
  { mode: 'entry', label: '数据填报', href: '/energy/entry' },
  { mode: 'reports', label: '能源报表', href: '/energy/reports' },
  { mode: 'analysis', label: '用量分析', href: '/energy/analysis' },
  { mode: 'data-quality', label: '数据质量', href: '/energy/data-quality' },
  { mode: 'settings', label: '配置管理', href: '/energy/settings' },
]

export function EnergyWorkspace({ mode }: { mode: EnergyMode }) {
  const params = useSearchParams()
  const options = useQuery({ queryKey: ['energy-ledger', 'options'], queryFn: () => ledgerRequest<Options>('/ledger-options') })
  return <main className={styles.workspace}>
    <Typography.Title level={3}>{PAGES.find(page => page.mode === mode)?.label}</Typography.Title>
    {mode === 'entry' ? <EnergyEntryClient manager={options.data?.is_manager ?? false} />
      : mode === 'settings' ? <EnergySettingsClient options={options.data} />
        : <EnergyReportsClient key={`${mode}:${params}`} mode={mode} />}
  </main>
}
