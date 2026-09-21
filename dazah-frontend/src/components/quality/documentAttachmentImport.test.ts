import { describe, expect, it } from 'vitest'
import { attachmentImportFeedback, documentAttachmentAccept } from './documentAttachmentImport'

describe('attachment import feedback', () => {
  it('allows all supported Word formats in the upload picker', () => {
    expect(documentAttachmentAccept.split(',')).toEqual(expect.arrayContaining(['.doc', '.docx', '.docm', '.wps']))
  })
  it('reports metadata and old attachment replacement on success', () => {
    const feedback = attachmentImportFeedback({ bound: 1, failed: 0, version_updated_count: 1, results: [] })
    expect(feedback.warning).toBe(false)
    expect(feedback.text).toContain('更新 1 个，未更新 0 个')
    expect(feedback.text).toContain('同步编号、生效日期并替换旧附件')
  })
  it.each([0, 1])('warns for rejected versions even with %i successful files', (bound) => {
    const feedback = attachmentImportFeedback({
      bound, failed: 1, version_updated_count: bound,
      results: [{ file_name: '同版本.docx', matched: false, match_type: 'none', version_updated: false,
        reason: '附件版本未高于当前版本，目录和附件均未更新' }],
    })
    expect(feedback.warning).toBe(true)
    expect(feedback.text).toContain('同版本.docx：附件版本未高于当前版本')
    expect(feedback.text).not.toContain('全部自动绑定')
  })
})
