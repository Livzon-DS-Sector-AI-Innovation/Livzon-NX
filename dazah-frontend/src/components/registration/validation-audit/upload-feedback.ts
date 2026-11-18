import { getUserErrorMessage } from '@/lib/user-error'
import type { components } from '@/types/generated/schema'

type UploadItem = components['schemas']['ValidationAuditUploadSuccess'] | components['schemas']['ValidationAuditUploadFailure']

export function summarizeUpload(items: UploadItem[]) {
  const failed = items.flatMap((item, index) => item.status === 'failed' ? [{ item, index }] : [])
  const problems = failed.slice(0, 3).map(({ item }) =>
    `${item.filename}：${getUserErrorMessage(undefined, '文件未能上传，请核对后重试', item.status_code)}`,
  )
  const succeeded = items.length - failed.length
  return {
    failedIndexes: new Set(failed.map(({ index }) => index)),
    succeeded,
    message: failed.length
      ? `上传成功 ${succeeded} 个，失败 ${failed.length} 个。${problems.join('；')}`
      : `已上传 ${succeeded} 个文件`,
  }
}
