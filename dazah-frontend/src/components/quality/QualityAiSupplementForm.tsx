'use client'

import { Alert, Button, Card, Input, Space } from 'antd'

interface QualityAiSupplementFormProps {
  value: string
  saving: boolean
  dirty: boolean
  onChange: (value: string) => void
  onSubmit: () => void
}

export function QualityAiSupplementForm({
  value,
  saving,
  dirty,
  onChange,
  onSubmit,
}: QualityAiSupplementFormProps) {
  return (
    <Card size="small" title="补充信息">
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Input.TextArea
          rows={6}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="补充调查说明、现场情况、原因线索、附件背景说明"
        />
        {dirty ? <Alert type="info" showIcon title="存在未应用补充信息" /> : null}
        <Button type="primary" loading={saving} onClick={onSubmit}>
          重新完善分析
        </Button>
      </Space>
    </Card>
  )
}
