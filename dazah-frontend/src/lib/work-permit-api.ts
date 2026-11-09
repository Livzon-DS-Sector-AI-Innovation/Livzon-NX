/**
 * 8 大作业票与特种作业证件的页面键与附件 URL 组装。
 * 独立于 "use server" 的 actions（Server Action 文件只能导出 async 函数）。
 */

export const WORK_PERMITS_PAGE_KEY = 'safety:ops-safety:work-permits'
export const WORK_CERTIFICATES_PAGE_KEY = 'safety:ops-safety:work-certificates'

export function certificateFileContentUrl(
  certificateId: string,
  fileId: string
): string {
  return `/api/v1/safety/work-certificates/${certificateId}/files/${fileId}/content`
}

export function certificateFilePreviewUrl(
  certificateId: string,
  fileId: string
): string {
  return `/api/v1/safety/work-certificates/${certificateId}/files/${fileId}/preview`
}

export function workPermitAttachmentPreviewUrl(
  permitId: string,
  attachmentId: string
): string {
  return `/api/v1/safety/work-permits/${permitId}/attachments/${attachmentId}/preview`
}

export function workPermitAttachmentContentUrl(
  permitId: string,
  attachmentId: string
): string {
  return `/api/v1/safety/work-permits/${permitId}/attachments/${attachmentId}/content`
}
