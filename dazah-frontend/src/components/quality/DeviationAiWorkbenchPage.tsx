'use client'

import { useCallback, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Descriptions, Space, Spin, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchDeviation, fetchFeishuDeviationReportRecord } from '@/lib/api/client/quality'

import type { DeviationAiWorkbenchRecord, DeviationDetail, FeishuDeviationReportRecordItem } from '@/types/quality'
import { DeviationAiConversationPanel } from './DeviationAiConversationPanel'

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

/** 本地偏差详情 → 工作台最小视图模型（spec：摘要只含编号/标题/部门/状态/发现日期） */
function toWorkbenchRecordFromDetail(detail: DeviationDetail): DeviationAiWorkbenchRecord {
  return {
    id: detail.id,
    deviation_code: detail.deviation_code || '',
    title: detail.title || null,
    department: detail.department || null,
    status: detail.status || '',
    discovery_date: detail.discovery_date || null,
  }
}

/** 飞书报告记录回退映射（本地无该偏差时，工作台基于报告记录进入） */
function toWorkbenchRecordFromReport(record: FeishuDeviationReportRecordItem): DeviationAiWorkbenchRecord {
  return {
    id: record.record_id || record.id,
    deviation_code: record.deviation_code || '',
    title: record.description || null,
    department: record.department || null,
    status: record.report_status || '',
    discovery_date: record.report_time || null,
  }
}

/**
 * 按 spec 优先复用 fetchDeviation() 拉取偏差详情；工作台也可能从飞书报告记录
 * （本地尚无对应偏差）进入，此时回退到报告记录接口。
 */
async function fetchWorkbenchRecord(id: string): Promise<DeviationAiWorkbenchRecord> {
  try {
    const detail = (await fetchDeviation(id)) as DeviationDetail
    if (detail && detail.id) {
      return toWorkbenchRecordFromDetail(detail)
    }
  } catch {
    // 本地不存在该偏差，回退飞书报告记录
  }
  const record = await fetchFeishuDeviationReportRecord(id)
  return toWorkbenchRecordFromReport(record)
}

export function DeviationAiWorkbenchPage() {
  const params = useParams<{ id: string }>()
  const { message } = App.useApp()
  const queryClient = useQueryClient()

  const { data: workbenchRecord, isLoading: loading, error } = useQuery<DeviationAiWorkbenchRecord>({
    queryKey: ['quality-deviation-ai', 'workbench', params.id],
    queryFn: () => fetchWorkbenchRecord(params.id),
    enabled: !!params.id,
  })

  const loadError = error
    ? getErrorMessage(error, '加载偏差工作台失败')
    : null

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载偏差工作台失败'))
    }
  }, [error, message])

  const handleApplied = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['quality-deviation-ai', 'workbench', params.id] })
  }, [queryClient, params.id])

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
          针对当前偏差报告补充上下文、上传附件，并生成偏差分析与 CAPA 建议。
        </Typography.Paragraph>
      </div>

      {loadError || !workbenchRecord ? (
        <Alert
          type="error"
          showIcon
          message="偏差工作台加载失败"
          description={loadError || '未找到对应的偏差记录'}
        />
      ) : (
        <>
          <Card size="small" title="偏差信息摘要">
            <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
              <Descriptions.Item label="偏差编号">{workbenchRecord.deviation_code}</Descriptions.Item>
              <Descriptions.Item label="标题">{workbenchRecord.title || '-'}</Descriptions.Item>
              <Descriptions.Item label="部门">{workbenchRecord.department || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">{workbenchRecord.status || '-'}</Descriptions.Item>
              <Descriptions.Item label="发现日期">{workbenchRecord.discovery_date || '-'}</Descriptions.Item>
            </Descriptions>
          </Card>

          <DeviationAiConversationPanel deviation={workbenchRecord} onApplied={handleApplied} />
        </>
      )}
    </div>
  )
}
