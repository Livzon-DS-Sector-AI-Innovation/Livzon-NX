'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { App, Button, Card, Descriptions, Space, Tag } from 'antd'
import { ArrowLeftOutlined, DeleteOutlined, DownloadOutlined, EditOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { deleteFeishuDeviationLedgerRecord } from '@/actions/quality'
import { exportFeishuDeviationLedgerRecord } from '@/lib/api/quality'
import type { FeishuDeviationLedgerRecordItem } from '@/types/quality'

const LEVEL_LABELS: Record<string, string> = {
  major: '重大',
  moderate: '次要',
  minor: '微小',
  '重大': '重大',
  '次要': '次要',
  '微小': '微小',
}

const LEVEL_OPTIONS = [
  { value: '重大', label: '重大' },
  { value: '次要', label: '次要' },
  { value: '微小', label: '微小' },
]

function normalizeLevelValue(value: string | null | undefined): string {
  if (!value) return ''
  return LEVEL_LABELS[value] || value
}

const booleanOptions = [
  { label: '是', value: 'true' },
  { label: '否', value: 'false' },
]

function formatDateTimeForInput(value: string | null | undefined): string {
  if (!value) return ''
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DDTHH:mm') : ''
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm') : value
}

function formatBoolean(value: boolean | null | undefined): string {
  if (value === true) return '是'
  if (value === false) return '否'
  return '-'
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export function DeviationDetail({
  initialDeviation = null,
  initialLoadError = null,
  initialEditMode = false,
  saveAction,
}: {
  initialDeviation?: FeishuDeviationLedgerRecordItem | null
  initialLoadError?: string | null
  initialEditMode?: boolean
  saveAction?: (formData: FormData) => void | Promise<void>
}) {
  const router = useRouter()
  const { message, modal } = App.useApp()
  const [editMode] = useState(initialEditMode)
  const [exporting, setExporting] = useState(false)
  const deviation = initialDeviation

  if (initialLoadError) {
    return (
      <Card>
        <div style={{ display: 'grid', gap: 16 }}>
          <div>加载飞书偏差台账失败：{initialLoadError}</div>
          <div>
            <Link href="/quality/deviations/ledger">
              <Button icon={<ArrowLeftOutlined />}>返回台账列表</Button>
            </Link>
          </div>
        </div>
      </Card>
    )
  }

  if (!deviation) {
    return (
      <Card>
        <div style={{ display: 'grid', gap: 16 }}>
          <div>未找到飞书偏差台账记录</div>
          <div>
            <Link href="/quality/deviations/ledger">
              <Button icon={<ArrowLeftOutlined />}>返回台账列表</Button>
            </Link>
          </div>
        </div>
      </Card>
    )
  }

  const detailHref = `/quality/deviations/${deviation.record_id}`
  const editHref = `${detailHref}?edit=1`

  const handleDelete = () => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除飞书偏差台账“${deviation.deviation_code || deviation.record_id}”吗？此操作不可恢复。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteFeishuDeviationLedgerRecord(deviation.record_id)
          message.success('飞书台账已删除')
          router.push('/quality/deviations/ledger')
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '删除失败'))
        }
      },
    })
  }

  const handleExport = async () => {
    try {
      setExporting(true)
      const { blob, filename } = await exportFeishuDeviationLedgerRecord(
        deviation.record_id
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '导出失败'))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Link href="/quality/deviations/ledger">
            <Button icon={<ArrowLeftOutlined />}>返回</Button>
          </Link>
          <h2 style={{ margin: 0 }}>{deviation.deviation_code || deviation.record_id}</h2>
          <Tag color={deviation.status === 'closed' ? 'green' : 'default'}>
            {deviation.status === 'closed' ? '已关闭' : '未关闭'}
          </Tag>
        </Space>
        <Space>
          <Button icon={<DownloadOutlined />} loading={exporting} onClick={() => void handleExport()}>
            导出Word
          </Button>
          {!editMode ? (
            <Link href={editHref}>
              <Button icon={<EditOutlined />}>编辑</Button>
            </Link>
          ) : (
            <>
              <Link href={detailHref}>
                <Button>取消</Button>
              </Link>
              <Button
                type="primary"
                {...(saveAction ? { htmlType: 'submit', form: 'deviation-edit-form' } : {})}
              >
                保存
              </Button>
            </>
          )}
          <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
            删除
          </Button>
        </Space>
      </div>

      {!editMode ? (
        <Card title="飞书台账详情">
          <Descriptions column={2}>
            <Descriptions.Item label="偏差编号">{deviation.deviation_code || '-'}</Descriptions.Item>
            <Descriptions.Item label="飞书记录ID">{deviation.record_id}</Descriptions.Item>
            <Descriptions.Item label="产品名称/批号">
              {deviation.affected_items || deviation.batch_number || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="偏差等级">
              {deviation.level ? LEVEL_LABELS[deviation.level] || deviation.level : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="偏差简要描述" span={2}>
              {deviation.description || deviation.title || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="偏差是否曾发生">
              {formatBoolean(deviation.has_occurred_before)}
            </Descriptions.Item>
            <Descriptions.Item label="是否关闭">
              {deviation.status === 'closed' ? '是' : '否'}
            </Descriptions.Item>
            <Descriptions.Item label="根本原因" span={2}>
              {deviation.root_cause_analysis || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="调查完成时间">
              {formatDateTime(deviation.investigation_completed_at)}
            </Descriptions.Item>
            <Descriptions.Item label="关闭时间">
              {formatDateTime(deviation.close_time)}
            </Descriptions.Item>
            <Descriptions.Item label="纠正预防措施" span={2}>
              {deviation.corrective_actions || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="产品/物料处理结果" span={2}>
              {deviation.material_disposition || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="飞书最近更新时间">
              {formatDateTime(deviation.feishu_source_updated_at || deviation.updated_at || deviation.created_at)}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {formatDateTime(deviation.created_at)}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      ) : (
        <Card title="编辑飞书台账">
          <form id="deviation-edit-form" action={saveAction}>
            <div style={{ display: 'grid', gap: 16 }}>
              <label style={{ display: 'grid', gap: 8 }}>
                <span>偏差编号</span>
                <input
                  value={deviation.deviation_code}
                  disabled
                  style={{
                    width: '100%',
                    minHeight: 44,
                    borderRadius: 8,
                    border: '1px solid #d9d9d9',
                    padding: '0 11px',
                    background: '#f5f5f5',
                  }}
                />
              </label>
              <label style={{ display: 'grid', gap: 8 }}>
                <span>产品名称/批号</span>
                <input
                  name="affected_items"
                  defaultValue={deviation.affected_items || ''}
                  style={{
                    width: '100%',
                    minHeight: 44,
                    borderRadius: 8,
                    border: '1px solid #d9d9d9',
                    padding: '0 11px',
                  }}
                />
              </label>
              <label style={{ display: 'grid', gap: 8 }}>
                <span>偏差简要描述</span>
                <textarea
                  name="description"
                  rows={4}
                  defaultValue={deviation.description || ''}
                  style={{
                    width: '100%',
                    borderRadius: 8,
                    border: '1px solid #d9d9d9',
                    padding: '8px 11px',
                  }}
                />
              </label>
              <label style={{ display: 'grid', gap: 8 }}>
                <span>偏差是否曾发生</span>
                <select
                  name="has_occurred_before"
                  defaultValue={
                    deviation.has_occurred_before === true
                      ? 'true'
                      : deviation.has_occurred_before === false
                        ? 'false'
                        : ''
                  }
                  style={{
                    width: '100%',
                    minHeight: 44,
                    borderRadius: 8,
                    border: '1px solid #d9d9d9',
                    padding: '0 11px',
                    background: '#fff',
                  }}
                >
                  <option value="">请选择</option>
                  {booleanOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ display: 'grid', gap: 8 }}>
                <span>根本原因</span>
                <textarea
                  name="root_cause_analysis"
                  rows={4}
                  defaultValue={deviation.root_cause_analysis || ''}
                  style={{
                    width: '100%',
                    borderRadius: 8,
                    border: '1px solid #d9d9d9',
                    padding: '8px 11px',
                  }}
                />
              </label>
              <label style={{ display: 'grid', gap: 8 }}>
                <span>偏差等级</span>
                <select
                  name="level"
                  defaultValue={normalizeLevelValue(deviation.level)}
                  style={{
                    width: '100%',
                    minHeight: 44,
                    borderRadius: 8,
                    border: '1px solid #d9d9d9',
                    padding: '0 11px',
                    background: '#fff',
                  }}
                >
                  <option value="">请选择</option>
                  {LEVEL_OPTIONS.map(({ value, label }) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ display: 'grid', gap: 8 }}>
                <span>调查完成时间</span>
                <input
                  name="investigation_completed_at"
                  type="datetime-local"
                  defaultValue={formatDateTimeForInput(deviation.investigation_completed_at)}
                  style={{
                    width: '100%',
                    minHeight: 44,
                    borderRadius: 8,
                    border: '1px solid #d9d9d9',
                    padding: '0 11px',
                  }}
                />
              </label>
              <label style={{ display: 'grid', gap: 8 }}>
                <span>纠正预防措施</span>
                <textarea
                  name="corrective_actions"
                  rows={4}
                  defaultValue={deviation.corrective_actions || ''}
                  style={{
                    width: '100%',
                    borderRadius: 8,
                    border: '1px solid #d9d9d9',
                    padding: '8px 11px',
                  }}
                />
              </label>
              <label style={{ display: 'grid', gap: 8 }}>
                <span>产品/物料处理结果</span>
                <textarea
                  name="material_disposition"
                  rows={4}
                  defaultValue={deviation.material_disposition || ''}
                  style={{
                    width: '100%',
                    borderRadius: 8,
                    border: '1px solid #d9d9d9',
                    padding: '8px 11px',
                  }}
                />
              </label>
              <label style={{ display: 'grid', gap: 8 }}>
                <span>是否关闭</span>
                <select
                  name="is_closed"
                  defaultValue={deviation.status === 'closed' ? 'true' : 'false'}
                  style={{
                    width: '100%',
                    minHeight: 44,
                    borderRadius: 8,
                    border: '1px solid #d9d9d9',
                    padding: '0 11px',
                    background: '#fff',
                  }}
                >
                  {booleanOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ display: 'grid', gap: 8 }}>
                <span>关闭时间</span>
                <input
                  name="close_time"
                  type="datetime-local"
                  defaultValue={formatDateTimeForInput(deviation.close_time)}
                  style={{
                    width: '100%',
                    minHeight: 44,
                    borderRadius: 8,
                    border: '1px solid #d9d9d9',
                    padding: '0 11px',
                  }}
                />
              </label>
            </div>
          </form>
        </Card>
      )}
    </div>
  )
}
