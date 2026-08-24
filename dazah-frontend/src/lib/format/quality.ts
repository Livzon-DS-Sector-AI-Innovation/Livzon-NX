import type {
  QualityFeishuSettingsTestResult,
  QualityPullSyncResult,
} from '@/types/quality'

export function formatQualitySyncSummary(
  result: Partial<QualityPullSyncResult> | null | undefined,
): string {
  const target = result?.entity_label ? `${result.entity_label}回拉完成` : '全模块回拉完成'
  return `${target}：同步 ${result?.synced || 0} 条，失败 ${result?.failed || 0} 条，冲突 ${result?.conflicts || 0} 条`
}

export function formatQualityFeishuTestSummary(
  result: Partial<QualityFeishuSettingsTestResult> | null | undefined,
): string {
  if (!result) return '测试完成'
  const prefix = result.success ? '连接成功' : '连接失败'
  return `${prefix}：${result.message || '未返回详细信息'}`
}
