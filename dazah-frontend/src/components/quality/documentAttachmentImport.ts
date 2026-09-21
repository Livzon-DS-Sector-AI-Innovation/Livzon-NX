import type { BatchImportDocumentAttachmentsResult } from '@/types/quality'

export const documentAttachmentAccept = '.doc,.docx,.docm,.wps,.pdf,.md'

export function attachmentImportFeedback(result: BatchImportDocumentAttachmentsResult) {
  const unchanged = (result.results ?? []).filter((item) => !item.version_updated)
  const detail = unchanged.slice(0, 3)
    .map((item) => `${item.file_name}：${item.reason ?? '未匹配到唯一目录'}`)
    .join('；')
  return {
    warning: result.failed > 0,
    text: `附件导入：更新 ${result.bound} 个，未更新 ${result.failed} 个。` +
      (result.bound > 0 ? '已同步编号、生效日期并替换旧附件。' : '') +
      (detail ? `未更新原因：${detail}${unchanged.length > 3 ? ' 等' : ''}` : ''),
  }
}
