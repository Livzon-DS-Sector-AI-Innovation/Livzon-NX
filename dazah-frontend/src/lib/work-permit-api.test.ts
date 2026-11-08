import { describe, expect, it } from 'vitest'

import {
  certificateFileContentUrl,
  certificateFilePreviewUrl,
  workPermitAttachmentContentUrl,
  workPermitAttachmentPreviewUrl,
} from './work-permit-api'

describe('work-permit url builders', () => {
  it('证件附件内容与预览地址', () => {
    expect(certificateFileContentUrl('c1', 'f1')).toBe(
      '/api/v1/safety/work-certificates/c1/files/f1/content',
    )
    expect(certificateFilePreviewUrl('c1', 'f1')).toBe(
      '/api/v1/safety/work-certificates/c1/files/f1/preview',
    )
  })

  it('作业票附件内容与预览地址', () => {
    expect(workPermitAttachmentPreviewUrl('p1', 'a1')).toBe(
      '/api/v1/safety/work-permits/p1/attachments/a1/preview',
    )
    expect(workPermitAttachmentContentUrl('p1', 'a1')).toBe(
      '/api/v1/safety/work-permits/p1/attachments/a1/content',
    )
  })
})
