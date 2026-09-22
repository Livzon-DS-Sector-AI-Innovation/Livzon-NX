'use client'

import { useState } from 'react'
import { App } from 'antd'
import { FeishuAttachmentPreviewModal } from './FeishuAttachmentPreviewModal'
import { renderFeishuValue } from './inspection/renderFeishuValue'

export function QualityRecordAttachments({
  recordId, attachments, basePath,
}: {
  recordId: string
  attachments: unknown
  basePath: string
}) {
  const { message } = App.useApp()
  const [preview, setPreview] = useState<{ name: string; url: string } | null>(null)
  const attachmentUrl = (_entity: string, id: string, token: string) =>
    `${basePath}/${encodeURIComponent(id)}/attachments/${encodeURIComponent(token)}/content`

  return <>
    {renderFeishuValue(attachments, { record_id: recordId }, 'oos_oot_report_record', message, {
      uiType: 'Attachment',
      attachmentUrlBuilder: attachmentUrl,
      onAttachmentPreview: ({ attachment }) => {
        if (!attachment.file_token) {
          if (attachment.url && /^https?:\/\//i.test(attachment.url)) {
            window.open(attachment.url, '_blank', 'noopener,noreferrer')
          } else {
            message.warning('该附件缺少有效链接或文件标识')
          }
          return
        }
        setPreview({ name: attachment.name || '附件', url: attachmentUrl('', recordId, attachment.file_token) })
      },
    })}
    {preview && <FeishuAttachmentPreviewModal
      open fileName={preview.name}
      previewSrc={preview.url.replace(/\/content$/, '/preview')}
      downloadSrc={preview.url}
      onClose={() => setPreview(null)}
    />}
  </>
}
