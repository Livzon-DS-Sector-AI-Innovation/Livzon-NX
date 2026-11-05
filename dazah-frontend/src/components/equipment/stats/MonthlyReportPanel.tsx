'use client'

// 月度健康报告面板（方案B收尾）：列表 + 生成 + Markdown 查看。
// 数据来自 GET /health/monthly-reports；生成走 Server Action（月度调度同款逻辑）。

import { useCallback, useEffect, useState } from 'react'
import { FileTextOutlined, ReloadOutlined } from '@ant-design/icons'
import { App, Button, DatePicker, Modal, Spin, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import ReactMarkdown from 'react-markdown'
import dayjs, { type Dayjs } from 'dayjs'
import type { MonthlyReport } from '@/types/equipment'
import { fetchMonthlyReportsClient } from '@/lib/api/equipment-client'
import { generateMonthlyReport } from '@/actions/equipment'

export function MonthlyReportPanel() {
  const { message } = App.useApp()
  const [reports, setReports] = useState<MonthlyReport[]>([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [viewing, setViewing] = useState<MonthlyReport | null>(null)
  const [month, setMonth] = useState<Dayjs | null>(dayjs().subtract(1, 'month'))

  const load = useCallback(async () => {
    const list = await fetchMonthlyReportsClient().catch(() => null)
    setReports(list ?? [])
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleGenerate = async () => {
    if (!month) {
      message.warning('请选择月份')
      return
    }
    setGenerating(true)
    try {
      await generateMonthlyReport(month.format('YYYY-MM'))
      message.success(`${month.format('YYYY-MM')} 报告已生成`)
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '生成失败')
    } finally {
      setGenerating(false)
    }
  }

  const columns: ColumnsType<MonthlyReport> = [
    {
      title: '月份',
      dataIndex: 'report_month',
      key: 'report_month',
      width: 90,
      render: (v: string) => <Tag color="purple">{v}</Tag>,
    },
    {
      title: '生成时间',
      dataIndex: 'generated_at',
      key: 'generated_at',
      width: 160,
      render: (v: string | null) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_: unknown, r) => (
        <Button size="small" type="link" onClick={() => setViewing(r)}>
          查看报告
        </Button>
      ),
    },
  ]

  return (
    <section
      style={{
        background: '#ffffff',
        borderRadius: 12,
        border: '1px solid #e5e3df',
        padding: '20px 24px',
      }}
      data-testid="monthly-report-panel"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <FileTextOutlined style={{ fontSize: 16, color: '#5645d4' }} />
        <span style={{ fontSize: 15, fontWeight: 600 }}>月度健康报告</span>
        <span style={{ color: '#8a867d', fontSize: 12 }}>
          每月 1 日 08:00 自动生成；也可按月补生成
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <DatePicker
            picker="month"
            value={month}
            onChange={(v) => setMonth(v)}
            allowClear={false}
          />
          <Button loading={generating} onClick={handleGenerate}>
            生成报告
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => { setLoading(true); void load(); }} />
        </div>
      </div>
      <Spin spinning={loading}>
        <Table<MonthlyReport>
          size="small"
          rowKey="id"
          columns={columns}
          dataSource={reports}
          pagination={false}
          locale={{ emptyText: '暂无报告，选择月份点「生成报告」' }}
        />
      </Spin>

      <Modal
        title={`设备月度健康报告 · ${viewing?.report_month ?? ''}`}
        open={!!viewing}
        onCancel={() => setViewing(null)}
        footer={null}
        width={760}
        styles={{ body: { maxHeight: '70vh', overflow: 'auto' } }}
      >
        <div className="monthly-report-md" style={{ fontSize: 14, lineHeight: 1.8 }}>
          <ReactMarkdown>{viewing?.content_md || '（无内容）'}</ReactMarkdown>
        </div>
      </Modal>
    </section>
  )
}
