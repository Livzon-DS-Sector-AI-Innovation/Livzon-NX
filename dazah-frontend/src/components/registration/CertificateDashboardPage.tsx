'use client'

import { useRef, useState, type ChangeEvent } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Row,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import { useRouter } from 'next/navigation'

import { importCertificateWorkbook } from '@/actions/registration'
import { CertificateManagementDashboard } from '@/components/registration'
import { fetchCertificateWorkbookExport } from '@/lib/api/client/registration'
import type {
  CertificateRecordSummary,
  CertificateReminderSetting,
  CertificateWorkbookOverview,
} from '@/types/registration'

interface CertificateDashboardPageProps {
  overview: CertificateWorkbookOverview
  reminderSettings: CertificateReminderSetting
}

function renderExpiryTag(status: string) {
  if (status === '已过期') {
    return <Tag color="red">{status}</Tag>
  }
  if (status === '90天内到期') {
    return <Tag color="orange">{status}</Tag>
  }
  if (status === '有效') {
    return <Tag color="green">{status}</Tag>
  }
  return <Tag>{status}</Tag>
}

const dashboardTableScroll = { x: 1100, y: 320 }

const recordColumns = [
  {
    title: '子表',
    dataIndex: 'sheet_name',
    key: 'sheet_name',
    width: 110,
    align: 'center' as const,
  },
  {
    title: '证照名称',
    dataIndex: 'certificate_name',
    key: 'certificate_name',
    width: 240,
    align: 'center' as const,
  },
  {
    title: '编号',
    dataIndex: 'certificate_number',
    key: 'certificate_number',
    width: 220,
    align: 'center' as const,
    render: (value?: string | null) => value || '—',
  },
  {
    title: '发证机关',
    dataIndex: 'authority',
    key: 'authority',
    width: 220,
    align: 'center' as const,
    render: (value?: string | null) => value || '—',
  },
  {
    title: '发证日期',
    dataIndex: 'issue_date',
    key: 'issue_date',
    width: 120,
    align: 'center' as const,
    render: (value?: string | null) => value || '—',
  },
  {
    title: '到期日期',
    dataIndex: 'expiry_date',
    key: 'expiry_date',
    width: 120,
    align: 'center' as const,
    render: (value?: string | null) => value || '—',
  },
  {
    title: '状态',
    dataIndex: 'expiry_status',
    key: 'expiry_status',
    width: 120,
    align: 'center' as const,
    render: renderExpiryTag,
  },
]

export default function CertificateDashboardPage({
  overview,
  reminderSettings,
}: CertificateDashboardPageProps) {
  const router = useRouter()
  const { message } = App.useApp()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [importingWorkbook, setImportingWorkbook] = useState(false)
  const [exportingWorkbook, setExportingWorkbook] = useState(false)

  const latestIssuedColumns = recordColumns.filter(
    (column) => column.key !== 'expiry_date' && column.key !== 'expiry_status'
  )

  async function handleWorkbookImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) {
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    setImportingWorkbook(true)
    try {
      const result = await importCertificateWorkbook(formData)
      message.success(
        result
          ? `导入成功，共覆盖 ${result.replaced_record_count} 条旧记录，写入 ${result.imported_record_count} 条新记录`
          : '导入成功'
      )
      router.refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '药政证书台账导入失败')
    } finally {
      setImportingWorkbook(false)
    }
  }

  async function handleWorkbookExport() {
    setExportingWorkbook(true)
    try {
      await fetchCertificateWorkbookExport()
      message.success('药政证书台账导出成功')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '药政证书台账导出失败')
    } finally {
      setExportingWorkbook(false)
    }
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ marginBottom: 0 }}>
        证书管理仪表盘
      </Typography.Title>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Space>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
            hidden
            onChange={handleWorkbookImport}
          />
          <Button onClick={() => fileInputRef.current?.click()} loading={importingWorkbook}>
            导入药政证书台账
          </Button>
          <Button type="primary" onClick={handleWorkbookExport} loading={exportingWorkbook}>
            导出药政证书台账
          </Button>
        </Space>
      </div>

      {overview.expired_count > 0 ? (
        <Alert
          type="warning"
          showIcon
          title={`当前共有 ${overview.expired_count} 份证书已过期，另有 ${overview.due_90_count} 份证书将在 90 天内到期。`}
        />
      ) : null}

      <CertificateManagementDashboard overview={overview} />

      <Card size="small" title="到期提醒状态">
        <Space wrap size={[8, 8]} align="center">
          <Tag color={reminderSettings.is_enabled ? 'processing' : 'default'}>
            {reminderSettings.is_enabled ? '已启用' : '未启用'}
          </Tag>
          <Tag color="purple">到期前 {reminderSettings.reminder_days} 天提醒</Tag>
          <Tag color="purple">当前规则命中 {reminderSettings.pending_count} 份待提醒证书</Tag>
          {reminderSettings.recipient_name ? (
            <Tag color="blue">
              当前通知人：{reminderSettings.recipient_name}
              {reminderSettings.recipient_department
                ? ` / ${reminderSettings.recipient_department}`
                : ''}
            </Tag>
          ) : null}
          <Typography.Text type="secondary">
            提醒开关、通知人与消息模板请在「注册管理 → 注册设置 → 通知设置」中维护。
          </Typography.Text>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12} style={{ display: 'flex' }}>
          <Card
            size="small"
            title="近期到期证书"
            style={{ width: '100%', height: '100%' }}
            styles={{ body: { paddingBottom: 12 } }}
          >
            <Table<CertificateRecordSummary>
              className="certificate-dashboard-table"
              rowKey="id"
              size="small"
              pagination={false}
              tableLayout="fixed"
              scroll={dashboardTableScroll}
              dataSource={overview.upcoming_expirations}
              columns={recordColumns}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12} style={{ display: 'flex' }}>
          <Card
            size="small"
            title="最新发证记录"
            style={{ width: '100%', height: '100%' }}
            styles={{ body: { paddingBottom: 12 } }}
          >
            <Table<CertificateRecordSummary>
              className="certificate-dashboard-table"
              rowKey="id"
              size="small"
              pagination={false}
              tableLayout="fixed"
              scroll={dashboardTableScroll}
              dataSource={overview.recent_issued}
              columns={latestIssuedColumns}
            />
          </Card>
        </Col>
      </Row>

      <style jsx global>{`
        .certificate-dashboard-table .ant-table-thead > tr > th {
          background: #faf8ff;
          border-bottom: 1px solid #e7dcff;
          text-align: center;
          font-size: 14px;
          line-height: 1.6;
          font-weight: 600;
          padding: 12px 8px;
        }

        .certificate-dashboard-table .ant-table-tbody > tr > td {
          text-align: center;
          vertical-align: middle;
          font-size: 14px;
          line-height: 1.7;
          padding: 12px 10px;
          border-bottom: 1px solid #f0f0f0;
          word-break: break-word;
        }

        .certificate-dashboard-table .ant-table-tbody > tr:nth-child(even) > td {
          background: #fcfcff;
        }

        .certificate-dashboard-table .ant-table-tbody > tr:hover > td {
          background: #f6f2ff;
        }
      `}</style>
    </Space>
  )
}
