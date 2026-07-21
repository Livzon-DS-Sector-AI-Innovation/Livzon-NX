'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Descriptions, Space, Spin, Typography } from 'antd'
import { fetchDeviation } from '@/lib/api/quality'
import type { DeviationAiWorkbenchRecord, DeviationDetail } from '@/types/quality'
import { DeviationAiConversationPanel } from './DeviationAiConversationPanel'

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function toWorkbenchRecord(deviation: DeviationDetail): DeviationAiWorkbenchRecord {
  return {
    id: deviation.id,
    deviation_code: deviation.deviation_code,
    title: deviation.title || '-',
    department: deviation.department,
    status: deviation.status,
    discovery_date: deviation.discovery_date,
  }
}

export function DeviationAiWorkbenchPage() {
  const params = useParams<{ id: string }>()
  const { message } = App.useApp()
  const [deviation, setDeviation] = useState<DeviationDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      setLoadError(null)
      const result = await fetchDeviation(params.id)
      setDeviation(result)
    } catch (error) {
      const nextError = getErrorMessage(error, '加载偏差工作台失败')
      setLoadError(nextError)
      message.error(nextError)
    } finally {
      setLoading(false)
    }
  }, [message, params.id])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const workbenchRecord = useMemo(
    () => (deviation ? toWorkbenchRecord(deviation) : null),
    [deviation]
  )

  if (loading) {
    return (
      <div style={{ display: 'grid', minHeight: 320, placeItems: 'center' }}>
        <Spin />
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div>
        <Space style={{ marginBottom: 12 }}>
          <Button icon={<ArrowLeftOutlined />} href="/quality/deviations/records">
            返回报告记录
          </Button>
        </Space>
        <Typography.Title level={3} style={{ margin: 0 }}>
          AI 工作台
        </Typography.Title>
        <Typography.Paragraph style={{ marginTop: 8, color: 'var(--color-steel)' }}>
          针对当前偏差补充上下文、上传附件，并生成偏差分析与 CAPA 建议。
        </Typography.Paragraph>
      </div>

      {loadError || !deviation || !workbenchRecord ? (
        <Alert
          type="error"
          showIcon
          message="偏差工作台加载失败"
          description={loadError || '未找到对应的偏差记录'}
        />
      ) : (
        <>
          <Card size="small" title={`偏差信息 / ${workbenchRecord.deviation_code}`}>
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="偏差编号">{workbenchRecord.deviation_code}</Descriptions.Item>
              <Descriptions.Item label="标题">{workbenchRecord.title}</Descriptions.Item>
              <Descriptions.Item label="部门">{workbenchRecord.department || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">{workbenchRecord.status || '-'}</Descriptions.Item>
              <Descriptions.Item label="发现日期">{workbenchRecord.discovery_date || '-'}</Descriptions.Item>
            </Descriptions>
          </Card>

          <DeviationAiConversationPanel deviation={workbenchRecord} onApplied={loadData} />
        </>
      )}
    </div>
  )
}
