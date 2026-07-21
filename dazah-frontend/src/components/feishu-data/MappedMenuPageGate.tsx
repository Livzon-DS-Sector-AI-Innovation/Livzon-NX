'use client'

import { Alert, Spin } from 'antd'
import { usePathname, useSearchParams } from 'next/navigation'
import type { ReactNode } from 'react'
import { useEffect, useMemo, useState } from 'react'

import {
  getFeishuMappedMenuTarget,
  type FeishuModuleCode,
} from '@/lib/feishu-data-source'
import { fetchMappedPageData } from '@/lib/api/mapped-feishu'
import type { WarehouseFeishuPageData } from '@/types/warehouse'

import { MappedDatasetPage } from './MappedDatasetPage'

interface MappedMenuPageGateProps {
  children: ReactNode
  moduleCode?: string
}

type LookupState =
  | { status: 'idle' | 'loading'; data?: undefined }
  | { status: 'ready'; targetKey: string; data: WarehouseFeishuPageData }
  | { status: 'error'; targetKey: string; message: string; data?: undefined }

const FEISHU_MODULES = new Set<FeishuModuleCode>(['production', 'energy', 'warehouse'])

function isFeishuModuleCode(value: string | undefined): value is FeishuModuleCode {
  return Boolean(value && FEISHU_MODULES.has(value as FeishuModuleCode))
}

export function MappedMenuPageGate({ children, moduleCode }: MappedMenuPageGateProps) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const serializedSearch = searchParams.toString()
  const supportedModule = isFeishuModuleCode(moduleCode) ? moduleCode : undefined
  const target = useMemo(
    () => supportedModule
      ? getFeishuMappedMenuTarget(
          supportedModule,
          pathname,
          new URLSearchParams(serializedSearch),
        )
      : undefined,
    [pathname, serializedSearch, supportedModule],
  )
  const [lookup, setLookup] = useState<LookupState>({ status: 'idle' })
  const targetKey = supportedModule && target
    ? `${supportedModule}:${target.value}`
    : undefined

  useEffect(() => {
    if (!supportedModule || !targetKey) return

    let cancelled = false
    const pageKey = targetKey.slice(targetKey.indexOf(':') + 1)
    fetchMappedPageData(supportedModule, pageKey)
      .then((data) => {
        if (!cancelled) setLookup({ status: 'ready', targetKey, data })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLookup({
            status: 'error',
            targetKey,
            message: error instanceof Error ? error.message : '读取页面数据映射失败',
          })
        }
      })

    return () => {
      cancelled = true
    }
  }, [supportedModule, targetKey])

  if (!supportedModule || !target || !targetKey) {
    return children
  }

  const currentLookup = (
    (lookup.status === 'ready' || lookup.status === 'error')
    && lookup.targetKey === targetKey
  ) ? lookup : undefined

  if (currentLookup?.status === 'error') {
    return (
      <div className="space-y-4">
        <Alert
          type="warning"
          showIcon
          message="读取页面数据映射失败，当前显示原页面内容"
          description={currentLookup.message}
        />
        {children}
      </div>
    )
  }

  if (!currentLookup || currentLookup.status !== 'ready') {
    return (
      <div className="flex min-h-[320px] items-center justify-center">
        <Spin tip="正在读取页面数据映射" size="large" />
      </div>
    )
  }

  if (!currentLookup.data.bindings?.length) return children

  return (
    <MappedDatasetPage
      moduleCode={supportedModule}
      pageKey={target.value}
      title={target.label}
      initialPageData={currentLookup.data}
    />
  )
}
