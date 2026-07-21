'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, App, Button, Card, Checkbox, Collapse, Empty, Space, Tag, Typography } from 'antd'
import {
  analyzeCapaAi,
  analyzeChangeAi,
  analyzeDeviationAi,
  applyQualityAiLog,
  suggestDeviationCapaAi,
} from '@/actions/quality'
import { fetchQualityAiLogs } from '@/lib/api/quality'
import type { QualityAiAnalysisLog } from '@/types/quality'

const { Paragraph, Text } = Typography

interface QualityAiPanelProps {
  entityType: 'deviation' | 'capa' | 'change'
  entityId: string
  onApplied?: () => void
}

function getLogTitle(log: QualityAiAnalysisLog): string {
  if (log.analysis_type === 'capa_suggestion') return 'CAPA建议'
  if (log.analysis_type === 'capa_review') return 'CAPA分析'
  if (log.analysis_type === 'change_impact') return '变更影响分析'
  return '偏差分析'
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

function getCapaAnalysisContextTip(log: QualityAiAnalysisLog): {
  type: 'success' | 'warning'
  message: string
  description: string
} | null {
  if (log.entity_type !== 'capa' || log.analysis_type !== 'capa_review') {
    return null
  }

  const inputSnapshot = log.input_snapshot || {}
  const analysisContext = inputSnapshot.analysis_context || {}
  const matchRule = analysisContext.match_rule as string | undefined
  const hasLinkedDeviation = Boolean(analysisContext.has_linked_deviation)

  if (hasLinkedDeviation) {
    const ruleLabelMap: Record<string, string> = {
      deviation_id: '显式 deviation_id',
      source_code: '来源编号 source_code',
      capa_code: 'CAPA 编号规则',
    }
    const ruleLabel = matchRule ? ruleLabelMap[matchRule] || matchRule : '关联规则'
    const linkedDeviationCode =
      inputSnapshot.linked_deviation?.deviation_code || inputSnapshot.capa?.source_code

    return {
      type: 'success',
      message: '本次分析已结合关联偏差',
      description: linkedDeviationCode
        ? `已纳入偏差 ${linkedDeviationCode} 的完整详情，匹配来源：${ruleLabel}。`
        : `已纳入关联偏差完整详情，匹配来源：${ruleLabel}。`,
    }
  }

  return {
    type: 'warning',
    message: '本次分析仅基于 CAPA 自身内容',
    description: '系统未识别到关联偏差，本次结论未结合偏差背景信息。',
  }
}

function renderLogContent(
  log: QualityAiAnalysisLog,
  selectedFields: string[],
  setSelectedFields: (values: string[]) => void
) {
  const contextTip = getCapaAnalysisContextTip(log)

  return (
    <>
      {log.error_message ? <Paragraph type="danger">{log.error_message}</Paragraph> : null}
      {contextTip ? (
        <Alert
          style={{ marginBottom: 12 }}
          type={contextTip.type}
          showIcon
          message={contextTip.message}
          description={contextTip.description}
        />
      ) : null}
      <Paragraph>
        <Text strong>摘要：</Text>
        {log.output_payload?.summary || '-'}
      </Paragraph>
      <Paragraph>
        <Text strong>风险等级：</Text>
        {log.output_payload?.risk_level || '-'}
      </Paragraph>
      <Paragraph>
        <Text strong>风险：</Text>
        {(log.output_payload?.risks || []).join('；') || '-'}
      </Paragraph>
      <Paragraph>
        <Text strong>建议：</Text>
        {(log.output_payload?.suggestions || []).join('；') || '-'}
      </Paragraph>
      <Paragraph>
        <Text strong>待补信息：</Text>
        {(log.output_payload?.missing_info || []).join('；') || '-'}
      </Paragraph>
      {log.applicable_fields.length > 0 ? (
        <Checkbox.Group value={selectedFields} onChange={(values) => setSelectedFields(values as string[])}>
          <div style={{ display: 'grid', gap: 8 }}>
            {log.applicable_fields.map((field) => (
              <Checkbox key={field.field_key} value={field.field_key}>
                {field.label}
              </Checkbox>
            ))}
          </div>
        </Checkbox.Group>
      ) : null}
    </>
  )
}

export function QualityAiPanel({ entityType, entityId, onApplied }: QualityAiPanelProps) {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [logs, setLogs] = useState<QualityAiAnalysisLog[]>([])
  const [selectedFieldsByLog, setSelectedFieldsByLog] = useState<Record<string, string[]>>({})

  const hydrateSelections = useCallback((items: QualityAiAnalysisLog[]) => {
    setSelectedFieldsByLog((prev) => {
      const next = { ...prev }
      for (const log of items) {
        if (!next[log.id]) {
          next[log.id] = log.applicable_fields.map((field) => field.field_key)
        }
      }
      return next
    })
  }, [])

  const upsertLog = useCallback(
    (log: QualityAiAnalysisLog) => {
      setLogs((prev) =>
        [log, ...prev.filter((item) => item.id !== log.id)].sort((a, b) =>
          b.created_at.localeCompare(a.created_at)
        )
      )
      hydrateSelections([log])
    },
    [hydrateSelections]
  )

  const loadLogs = useCallback(async () => {
    try {
      const result = await fetchQualityAiLogs({
        entity_type: entityType,
        entity_id: entityId,
        page: 1,
        page_size: 20,
      })
      setLogs(result.items)
      hydrateSelections(result.items)
    } catch (error) {
      message.error(getErrorMessage(error, '加载 AI 记录失败'))
    }
  }, [entityId, entityType, hydrateSelections, message])

  useEffect(() => {
    void Promise.resolve().then(loadLogs)
  }, [loadLogs])

  const actionButtons = useMemo(() => {
    if (entityType === 'deviation') {
      return [
        {
          key: 'analyze',
          label: 'AI分析',
          action: async () => analyzeDeviationAi(entityId),
          success: '偏差 AI 分析已完成',
        },
        {
          key: 'suggest-capa',
          label: '生成CAPA建议',
          action: async () => suggestDeviationCapaAi(entityId),
          success: 'CAPA 建议已生成',
        },
      ]
    }
    if (entityType === 'capa') {
      return [
        {
          key: 'analyze',
          label: '检查措施质量',
          action: async () => analyzeCapaAi(entityId),
          success: 'CAPA AI 分析已完成',
        },
      ]
    }
    return [
      {
        key: 'analyze',
        label: '生成影响清单',
        action: async () => analyzeChangeAi(entityId),
        success: '变更 AI 分析已完成',
      },
    ]
  }, [entityId, entityType])

  const groupedLogs = useMemo(() => {
    return logs.reduce<Record<string, QualityAiAnalysisLog[]>>((acc, log) => {
      const key = log.analysis_type || 'unknown'
      if (!acc[key]) {
        acc[key] = []
      }
      acc[key].push(log)
      return acc
    }, {})
  }, [logs])

  const latestLogs = useMemo(() => {
    return Object.values(groupedLogs)
      .map((items) => items[0])
      .filter((item): item is QualityAiAnalysisLog => Boolean(item))
  }, [groupedLogs])

  const historyLogs = useMemo(() => {
    return Object.values(groupedLogs).flatMap((items) => items.slice(1))
  }, [groupedLogs])

  const handleAnalyze = useCallback(
    async (runner: () => Promise<QualityAiAnalysisLog | null>, successMessage: string) => {
      try {
        setLoading(true)
        const createdLog = await runner()
        if (createdLog) {
          upsertLog(createdLog)
        }
        message.success(successMessage)
        await loadLogs()
        onApplied?.()
      } catch (error) {
        message.error(getErrorMessage(error, 'AI 分析失败'))
      } finally {
        setLoading(false)
      }
    },
    [loadLogs, message, onApplied, upsertLog]
  )

  const handleApply = useCallback(
    async (log: QualityAiAnalysisLog) => {
      const selected = selectedFieldsByLog[log.id] || []
      if (selected.length === 0) {
        message.warning('请先选择要应用的字段')
        return
      }
      try {
        setLoading(true)
        const updatedLog = await applyQualityAiLog(log.id, selected)
        if (updatedLog) {
          upsertLog(updatedLog)
        }
        message.success('AI 建议已应用')
        await loadLogs()
        onApplied?.()
      } catch (error) {
        message.error(getErrorMessage(error, '应用 AI 建议失败'))
      } finally {
        setLoading(false)
      }
    },
    [loadLogs, message, onApplied, selectedFieldsByLog, upsertLog]
  )

  return (
    <Card title="AI辅助分析" extra={<Button onClick={loadLogs}>刷新</Button>}>
      <Space wrap style={{ marginBottom: 16 }}>
        {actionButtons.map((item) => (
          <Button
            key={item.key}
            type="primary"
            loading={loading}
            onClick={() => handleAnalyze(item.action, item.success)}
          >
            {item.label}
          </Button>
        ))}
      </Space>

      {logs.length === 0 ? (
        <Empty description="暂无 AI 分析记录" />
      ) : (
        <div style={{ display: 'grid', gap: 16 }}>
          <Typography.Text type="secondary">
            默认展示每种分析类型的最新结果，历史记录可在下方展开查看。
          </Typography.Text>
          {latestLogs.map((log) => (
            <Card
              key={log.id}
              size="small"
              title={
                <Space>
                  <span>{getLogTitle(log)}</span>
                  <Tag color={log.status === 'completed' ? 'green' : 'red'}>
                    {log.status === 'completed' ? '成功' : '失败'}
                  </Tag>
                  <Tag color="gold">最新</Tag>
                  {log.is_applied ? <Tag color="blue">已应用</Tag> : null}
                </Space>
              }
              extra={
                log.applicable_fields.length > 0 && log.status === 'completed' ? (
                  <Button size="small" onClick={() => handleApply(log)} loading={loading}>
                    应用到字段
                  </Button>
                ) : null
              }
            >
              {renderLogContent(log, selectedFieldsByLog[log.id] || [], (values) =>
                setSelectedFieldsByLog((prev) => ({
                  ...prev,
                  [log.id]: values,
                }))
              )}
            </Card>
          ))}
          {historyLogs.length > 0 ? (
            <Collapse
              items={[
                {
                  key: 'history',
                  label: `查看历史记录（${historyLogs.length}）`,
                  children: (
                    <div style={{ display: 'grid', gap: 12 }}>
                      {historyLogs.map((log) => (
                        <Card
                          key={log.id}
                          size="small"
                          title={
                            <Space>
                              <span>{getLogTitle(log)}</span>
                              <Tag color={log.status === 'completed' ? 'green' : 'red'}>
                                {log.status === 'completed' ? '成功' : '失败'}
                              </Tag>
                              {log.is_applied ? <Tag color="blue">已应用</Tag> : null}
                            </Space>
                          }
                        >
                          {renderLogContent(log, selectedFieldsByLog[log.id] || [], (values) =>
                            setSelectedFieldsByLog((prev) => ({
                              ...prev,
                              [log.id]: values,
                            }))
                          )}
                        </Card>
                      ))}
                    </div>
                  ),
                },
              ]}
            />
          ) : null}
        </div>
      )}
    </Card>
  )
}
