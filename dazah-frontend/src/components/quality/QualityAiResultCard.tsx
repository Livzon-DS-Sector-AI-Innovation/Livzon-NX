'use client'

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Checkbox, Empty, Space, Tag, Typography } from 'antd'
import type { DeviationAiSessionResultPayload } from '@/types/quality'

const { Paragraph, Text } = Typography

interface QualityAiResultCardProps {
  title: string
  payload: DeviationAiSessionResultPayload | null
  section: 'deviation_analysis' | 'capa_suggestion'
  loading: boolean
  onApply: (section: 'deviation_analysis' | 'capa_suggestion', fieldKeys: string[]) => Promise<void>
}

export function QualityAiResultCard({
  title,
  payload,
  section,
  loading,
  onApply,
}: QualityAiResultCardProps) {
  const [selectedFields, setSelectedFields] = useState<string[]>([])

  useEffect(() => {
    setSelectedFields(payload?.applicable_fields.map((field) => field.field_key) || [])
  }, [payload])

  return (
    <Card
      size="small"
      title={
        <Space>
          <span>{title}</span>
          <Tag color="blue">当前结果</Tag>
        </Space>
      }
      extra={
        payload && payload.applicable_fields.length > 0 ? (
          <Button
            size="small"
            type="primary"
            loading={loading}
            onClick={() => void onApply(section, selectedFields)}
          >
            应用到字段
          </Button>
        ) : null
      }
    >
      {!payload ? (
        <Empty description={`当前暂无${title}结果，请补充信息后重新完善分析。`} />
      ) : (
        <>
          <Paragraph>
            <Text strong>摘要：</Text>
            {payload.summary || '-'}
          </Paragraph>
          {'risk_level' in payload ? (
            <Paragraph>
              <Text strong>风险等级：</Text>
              {payload.risk_level || '-'}
            </Paragraph>
          ) : null}
          <Paragraph>
            <Text strong>风险：</Text>
            {payload.risks.join('；') || '-'}
          </Paragraph>
          <Paragraph>
            <Text strong>建议：</Text>
            {payload.suggestions.join('；') || '-'}
          </Paragraph>
          <Paragraph>
            <Text strong>待补信息：</Text>
            {payload.missing_info.join('；') || '-'}
          </Paragraph>
          {payload.disclaimer ? (
            <Alert showIcon type="info" style={{ marginBottom: 12 }} message={payload.disclaimer} />
          ) : null}
          {payload.applicable_fields.length > 0 ? (
            <Checkbox.Group value={selectedFields} onChange={(values) => setSelectedFields(values as string[])}>
              <div style={{ display: 'grid', gap: 8 }}>
                {payload.applicable_fields.map((field) => (
                  <Checkbox key={field.field_key} value={field.field_key}>
                    {field.label}
                  </Checkbox>
                ))}
              </div>
            </Checkbox.Group>
          ) : null}
        </>
      )}
    </Card>
  )
}
