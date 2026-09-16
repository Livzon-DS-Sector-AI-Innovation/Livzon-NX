'use client'

import { useState } from 'react'
import { App, Button, DatePicker } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'

import { InspectionFeishuTable } from '@/components/quality/inspection'

/** 设备维护保养记录页：台账 + 完成即生成下一期任务 + 按月汇总导出。 */
export function MaintenanceRecordsPage() {
  const { message } = App.useApp()
  /** 月份为空 = 不按月过滤（看全部）；选中 = 列表按「生成日期」落在当月过滤 */
  const [month, setMonth] = useState<Dayjs | null>(dayjs())
  const [exporting, setExporting] = useState(false)

  const handleExport = async () => {
    if (!month) {
      message.warning('导出按月汇总，请先选择月份')
      return
    }
    setExporting(true)
    try {
      const params = new URLSearchParams({ month: month.format('YYYY-MM') })
      const res = await fetch(
        `/api/v1/quality/instruments/maintenance/export?${params.toString()}`,
        { cache: 'no-store' },
      )
      if (!res.ok) {
        let msg = `导出失败(${res.status})`
        try {
          const errJson = await res.json()
          if (errJson?.message) msg = errJson.message
        } catch { /* 非 JSON 错误体则用默认文案 */ }
        throw new Error(msg)
      }
      const blob = await res.blob()
      const downloadUrl = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = downloadUrl
      link.download = `${month.format('YYYY年M月')}  设备年度预防性维护保养汇总表.xlsx`
      link.click()
      window.URL.revokeObjectURL(downloadUrl)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '导出失败')
    } finally {
      setExporting(false)
    }
  }

  return (
    <InspectionFeishuTable
      title="设备维护保养记录"
      listApi="/api/v1/quality/instruments/maintenance"
      pullApi="/api/v1/quality/instruments/maintenance/pull"
      entityCode="qc_instr_maintenance"
      monthFilter={month ? month.format('YYYY-MM') : ''}
      editable
      editablePersonFields
      enableAttachmentPreview
      showLastSyncTime
      filters={[
        { key: '是否完成', label: '是否完成' },
        { key: '维保类型', label: '维保类型' },
      ]}
      /* 公式列头太长：页面只显示「剩余天数」；维护内容加宽便于阅读 */
      columnLabels={{ '剩余天数（提前1周通知）': '剩余天数' }}
      columnWidths={{
        '剩余天数（提前1周通知）': 90,
        维护内容: 220,
      }}
      valueTags={{
        是否完成: { 是: { color: 'green' }, 否: { color: 'red' } },
      }}
      cellHighlights={{
        /* 剩余天数：未完成时 ≤3 天红、≤7 天橙，其他正常 */
        '剩余天数（提前1周通知）': (record) => {
          if (record['是否完成'] === '是') return null
          const days = Number(record['剩余天数（提前1周通知）'])
          if (Number.isNaN(days)) return null
          if (days <= 3) return { color: 'red' }
          if (days <= 7) return { color: 'orange' }
          return null
        },
      }}
      toolbarContent={
        <>
          <DatePicker
            picker="month"
            allowClear
            value={month}
            onChange={value => setMonth(value)}
            placeholder="全部月份"
            style={{ width: 120 }}
          />
          <Button
            icon={<DownloadOutlined />}
            loading={exporting}
            onClick={handleExport}
          >
            导出汇总表
          </Button>
        </>
      }
    />
  )
}