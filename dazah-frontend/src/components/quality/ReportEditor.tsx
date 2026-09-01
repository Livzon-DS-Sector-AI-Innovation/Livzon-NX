'use client'

import { qualityTokens } from './themeTokens'
import { useState, useCallback } from 'react'
import { App, Card, Button, Input, Space, List, Typography } from 'antd'
import { SaveOutlined, EditOutlined, HistoryOutlined, ArrowLeftOutlined, EyeOutlined, FileTextOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import type { ReportVersion, InvestigationRecord } from '@/types/quality'

const { TextArea } = Input
const { Text, Paragraph } = Typography

interface ReportEditorProps {
  initialContent: string
  versions: ReportVersion[]
  investigationRecords: InvestigationRecord[]
  onSave: (content: string) => Promise<void>
  readOnly?: boolean
}

function generateReportFromRecords(records: InvestigationRecord[]): string {
  if (records.length === 0) return ''
  let text = '调查报告\n\n'
  records.forEach((record, index) => {
    text += `调查记录 ${index + 1}\n`
    if (record.nonconformityDescription) {
      text += `不符合事项描述：${record.nonconformityDescription}\n`
    }
    if (record.rootCauseAnalysis) {
      text += `根本原因分析：${record.rootCauseAnalysis}\n`
    }
    if (record.riskAssessment) {
      text += `风险评估：${record.riskAssessment}\n`
    }
    if (record.urgentMeasures) {
      text += `紧急处理措施：${record.urgentMeasures}\n`
    }
    if (record.capaProposals && record.capaProposals.length > 0) {
      text += 'CAPA建议：\n'
      record.capaProposals.forEach((p) => {
        text += `  ${p.summary} — 执行人：${p.executor} — 预计完成日期：${p.expectedCompletionDate}\n`
      })
    }
    text += '\n'
  })
  return text
}

export function ReportEditor({
  initialContent,
  versions,
  investigationRecords,
  onSave,
  readOnly = false,
}: ReportEditorProps) {
  const { message } = App.useApp()
  const [content, setContent] = useState(initialContent)
  const [isEditing, setIsEditing] = useState(!readOnly && !initialContent)
  const [showVersionHistory, setShowVersionHistory] = useState(false)
  const [viewingVersion, setViewingVersion] = useState<ReportVersion | null>(null)
  const [saving, setSaving] = useState(false)

  // content tracks initialContent via key prop on parent (no sync needed in render)

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(content)
      message.success('保存成功')
      setIsEditing(false)
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleGenerate = useCallback(() => {
    const generated = generateReportFromRecords(investigationRecords)
    if (!generated) {
      message.info('暂无调查记录可生成报告')
      return
    }
    setContent(generated)
    setIsEditing(true)
    message.success('已从调查记录生成报告内容')
  }, [investigationRecords, message])

  const isViewingHistory = viewingVersion !== null
  const displayContent = isViewingHistory ? viewingVersion.content : content
  const effectiveReadOnly = readOnly || isViewingHistory || !isEditing
  const hasRecords = investigationRecords.length > 0
  const isEmpty = !displayContent

  return (
    <Card
      title={
        <Space>
          <FileTextOutlined />
          <span>调查报告</span>
        </Space>
      }
      extra={
        <Space>
          {isViewingHistory ? (
            <Button icon={<ArrowLeftOutlined />} onClick={() => setViewingVersion(null)}>
              返回当前版本
            </Button>
          ) : (
            <>
              {isEditing ? (
                <>
                  <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
                    保存
                  </Button>
                  <Button onClick={() => setIsEditing(false)}>取消</Button>
                </>
              ) : !readOnly ? (
                <>
                  <Button icon={<EditOutlined />} onClick={() => setIsEditing(true)}>
                    编辑
                  </Button>
                  <Button
                    icon={<HistoryOutlined />}
                    onClick={() => {
                      setShowVersionHistory(!showVersionHistory)
                      setViewingVersion(null)
                    }}
                  >
                    历史版本{versions.length > 0 && `(${versions.length})`}
                  </Button>
                </>
              ) : null}
            </>
          )}
        </Space>
      }
    >
      {isViewingHistory && (
        <div style={{ marginBottom: 16, padding: '8px 12px', background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
          <EyeOutlined />
          <Text>正在查看历史版本 — {dayjs(viewingVersion!.editTime).format('YYYY-MM-DD HH:mm')}</Text>
          <Button size="small" type="link" style={{ marginLeft: 'auto' }} onClick={() => setViewingVersion(null)}>
            返回当前
          </Button>
        </div>
      )}
      <div style={{ display: 'flex' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {!isEditing && isEmpty && !readOnly ? (
            <div style={{ minHeight: 400, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16, border: '2px dashed #d9d9d9', borderRadius: 8, color: '#999' }}>
              <p>暂无调查报告内容</p>
              <Space>
                {hasRecords && (
                  <Button icon={<FileTextOutlined />} onClick={handleGenerate}>
                    从调查记录生成
                  </Button>
                )}
                <Button icon={<EditOutlined />} onClick={() => setIsEditing(true)}>
                  手动编辑
                </Button>
              </Space>
            </div>
          ) : effectiveReadOnly ? (
            <div style={{ minHeight: 400, padding: 16, background: qualityTokens.bgSoft, borderRadius: 4, whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
              {displayContent || <Text type="secondary">暂无内容</Text>}
            </div>
          ) : (
            <TextArea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="请输入调查报告内容..."
              autoSize={{ minRows: 15, maxRows: 30 }}
              style={{ fontFamily: 'inherit' }}
            />
          )}
        </div>
        {showVersionHistory && (
          <div style={{ width: 280, marginLeft: 16, borderLeft: '1px solid #f0f0f0', paddingLeft: 16 }}>
            <div style={{ marginBottom: 12 }}>
              <Text strong>版本历史</Text>
              <Button
                type="text"
                size="small"
                block
                onClick={() => setViewingVersion(null)}
                style={{ textAlign: 'left', marginTop: 8 }}
              >
                当前版本
              </Button>
            </div>
            <div style={{ maxHeight: 500, overflowY: 'auto' }}>
              {versions.length === 0 ? (
                <Text type="secondary" style={{ fontSize: 12 }}>暂无历史版本</Text>
              ) : (
                <List
                  size="small"
                  dataSource={versions}
                  renderItem={(version: ReportVersion, index: number) => (
                    <List.Item
                      style={{
                        padding: '8px 12px',
                        cursor: 'pointer',
                        background: viewingVersion === version ? '#e6f7ff' : undefined,
                        borderRadius: 4,
                        marginBottom: 4,
                      }}
                      onClick={() => setViewingVersion(version)}
                    >
                      <div>
                        <Text style={{ fontSize: 12 }}>
                          {dayjs(version.editTime).format('YYYY-MM-DD HH:mm')}
                        </Text>
                        {version.changeSummary && (
                          <Paragraph
                            ellipsis
                            style={{ fontSize: 12, marginBottom: 0, marginTop: 4 }}
                            type="secondary"
                          >
                            {version.changeSummary}
                          </Paragraph>
                        )}
                      </div>
                    </List.Item>
                  )}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}
