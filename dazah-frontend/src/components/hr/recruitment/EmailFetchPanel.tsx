'use client'

import React from 'react'
import { Button, Tag, App } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { fetchEmailConfig } from '@/lib/api/hr'
import { triggerEmailFetch } from '@/actions/hr'

export default function EmailFetchPanel() {
  const { message } = App.useApp()
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['email-config'],
    queryFn: fetchEmailConfig,
    refetchInterval: 30000,
  })

  const config = data?.data
  const configured = !!config?.fetch_enabled
  const [fetching, setFetching] = React.useState(false)

  const handleFetchNow = async () => {
    setFetching(true)
    try {
      const res = await triggerEmailFetch()
      message.success(res.message || '抓取完成')
      refetch()
    } catch (err) { message.error((err instanceof Error ? err.message : '') || '抓取失败') }
    finally { setFetching(false) }
  }

  const formatScanTime = (scanAt: string | null | undefined) => {
    if (!scanAt) return '-'
    try { return new Date(scanAt).toLocaleString('zh-CN') } catch { return scanAt }
  }

  const getStatusTag = (status: string | null | undefined, fetchEnabled: boolean) => {
    if (!fetchEnabled) return <Tag color="default" style={{ fontSize: 12 }}>未启用</Tag>
    if (!status) return <Tag color="processing" style={{ fontSize: 12 }}>从未抓取</Tag>
    switch (status) {
      case 'ok': return <Tag color="success" style={{ fontSize: 12 }}>正常</Tag>
      case 'error': return <Tag color="error" style={{ fontSize: 12 }}>异常</Tag>
      case 'not_configured_or_disabled': return <Tag color="default" style={{ fontSize: 12 }}>未配置</Tag>
      default: return <Tag style={{ fontSize: 12 }}>{status}</Tag>
    }
  }

  return (
    <div className="bg-white rounded-xl border border-[#e5e3df] shadow-sm px-4 py-2.5">
      <div className="flex items-center gap-4 text-xs">
        <span className="text-gray-500 font-medium whitespace-nowrap">邮箱抓取</span>
        <span className="flex items-center gap-1.5">
          <span className="text-gray-400">状态</span>
          {getStatusTag(config?.last_fetch_status, configured)}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-gray-400">上次扫描</span>
          <span className="text-gray-700 font-medium">{formatScanTime(config?.last_scan_at)}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-gray-400">最近抓取</span>
          <span className="text-gray-700 font-medium">{config?.last_fetched_count ?? 0} 份</span>
        </span>
        <span className="flex items-center gap-1.5 flex-1 min-w-0">
          <span className="text-gray-400 whitespace-nowrap">保存路径</span>
          <span className="text-gray-500 truncate" title={config?.watch_dir}>{config?.watch_dir || '-'}</span>
        </span>
        {configured && (
          <Button size="small" loading={fetching} onClick={handleFetchNow} style={{ fontSize: 12 }}>
            手动抓取
          </Button>
        )}
        <Button size="small" icon={<ReloadOutlined />} onClick={() => refetch()} loading={isLoading} style={{ fontSize: 12 }} />
      </div>
    </div>
  )
}
