'use client'

import { ExportOutlined } from '@ant-design/icons'
import { Button, Card, Typography } from 'antd'

import { TOBACCO_GIFT_REQUISITION_FORM_URL } from '@/lib/administration-pages'

/** 领用申请入口：跳转飞书表单，提交后由定时镜像同步进平台。 */
export default function TobaccoGiftRequisitionCard() {
  return (
    <Card size="small" className="!mb-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Typography.Text type="secondary">
          领用申请通过飞书表单提交，提交后最长约 15 分钟自动同步到本台账（也可在飞书设置页手动同步）。
        </Typography.Text>
        <Button
          type="primary"
          icon={<ExportOutlined />}
          href={TOBACCO_GIFT_REQUISITION_FORM_URL}
          target="_blank"
          rel="noreferrer"
        >
          领用申请（飞书表单）
        </Button>
      </div>
    </Card>
  )
}
