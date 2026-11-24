'use client'

import { ExportOutlined } from '@ant-design/icons'
import { Button } from 'antd'

import { TOBACCO_GIFT_REQUISITION_FORM_URL } from '@/lib/administration-pages'

/** 领用申请：跳转飞书表单，提交后由定时镜像同步进平台。 */
export default function TobaccoGiftApplyButton() {
  return (
    <Button
      type="primary"
      icon={<ExportOutlined />}
      href={TOBACCO_GIFT_REQUISITION_FORM_URL}
      target="_blank"
      rel="noreferrer"
    >
      领用申请
    </Button>
  )
}
