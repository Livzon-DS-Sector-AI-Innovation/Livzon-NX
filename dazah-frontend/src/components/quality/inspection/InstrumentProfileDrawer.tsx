'use client'

import { useMemo } from 'react'
import { Alert, Descriptions, Drawer, Space, Spin, Table, Tabs, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { fetchInstrumentProfile } from '@/lib/api/client/quality'
import type { InstrumentProfileData } from '@/types/quality'

const { Text } = Typography

const DAY_MS = 24 * 60 * 60 * 1000
const EXCEL_EPOCH_MS = Date.UTC(1899, 11, 30)

/** 档案里按列名识别的日期列（值为毫秒时间戳或 Excel 序列号） */
const DATE_COLUMN_NAMES = new Set([
  '入厂日期',
  '生成日期',
  '完成日期',
  '下次维保时间',
  '维修时间',
  '校验时间',
  '校验有效期',
  '计划校验时间',
  '检定日期',
  '下次检定日期',
  '有效期',
  '购买维保合同时间',
])

function formatDateCell(value: unknown): string | null {
  const text = typeof value === 'string' ? value.trim() : ''
  const numeric =
    typeof value === 'number'
      ? value
      : /^\d+(\.\d+)?$/.test(text)
        ? Number(text)
        : Number.NaN
  if (!Number.isFinite(numeric) || numeric <= 0) return null
  const ms = numeric > 1e11 ? numeric : numeric <= 400000 ? EXCEL_EPOCH_MS + Math.round(numeric) * DAY_MS : Number.NaN
  if (!Number.isFinite(ms)) return null
  const target = new Date(ms)
  if (Number.isNaN(target.getTime())) return null
  const y = target.getFullYear()
  const m = `${target.getMonth() + 1}`.padStart(2, '0')
  const d = `${target.getDate()}`.padStart(2, '0')
  return `${y}-${m}-${d}`
}

function cellText(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  if (Array.isArray(value)) {
    return value
      .map((item) =>
        item && typeof item === 'object'
          ? String((item as { name?: string }).name ?? (item as { text?: string }).text ?? '')
          : String(item),
      )
      .filter(Boolean)
      .join('、')
  }
  if (typeof value === 'object') {
    const obj = value as { name?: string; text?: string; link?: string }
    return String(obj.name ?? obj.text ?? obj.link ?? '')
  }
  return String(value)
}

/** 依据行数据动态建列（列序 = 首次出现顺序），日期/人员/链接按值形态渲染 */
function useProfileColumns(rows: Record<string, unknown>[]) {
  return useMemo(() => {
    const keys: string[] = []
    const seen = new Set<string>()
    for (const row of rows) {
      for (const key of Object.keys(row)) {
        if (key === 'record_id' || key === 'created_at' || key === 'updated_at') continue
        if (!seen.has(key)) {
          seen.add(key)
          keys.push(key)
        }
      }
    }
    const columns: ColumnsType<Record<string, unknown>> = keys.map((key) => ({
      title: key,
      dataIndex: key,
      key,
      render: (value: unknown) => {
        if (DATE_COLUMN_NAMES.has(key)) {
          const formatted = formatDateCell(value)
          if (formatted) return formatted
        }
        const text = cellText(value)
        return text || '-'
      },
    }))
    return columns
  }, [rows])
}

function ProfileSectionTable({ rows }: { rows: Record<string, unknown>[] }) {
  const columns = useProfileColumns(rows)
  if (rows.length === 0) {
    return <Text type="secondary">暂无记录</Text>
  }
  return (
    <Table
      rowKey="record_id"
      size="small"
      columns={columns}
      dataSource={rows}
      pagination={rows.length > 10 ? { pageSize: 10, showSizeChanger: false } : false}
      scroll={{ x: 'max-content' }}
    />
  )
}

interface InstrumentProfileDrawerProps {
  open: boolean
  /** 仪器台账行（取 record_id 与展示名） */
  record?: Record<string, unknown> | null
  onClose: () => void
}

/** 仪器档案：按设备编号匹配该仪器的维保/维修/校验/合同情况。 */
export function InstrumentProfileDrawer({
  open,
  record,
  onClose,
}: InstrumentProfileDrawerProps) {
  const recordId = record ? String(record.record_id ?? '') : ''
  const { data, isLoading, error } = useQuery<InstrumentProfileData, Error>({
    queryKey: ['quality-instruments', 'profile', recordId],
    queryFn: () => fetchInstrumentProfile(recordId),
    enabled: open && Boolean(recordId),
  })

  const equipmentEntries = useMemo(() => {
    if (!data?.equipment) return []
    return Object.entries(data.equipment)
      .filter(([key]) => key !== 'record_id' && key !== 'created_at' && key !== 'updated_at')
      .map(([key, value]) => {
        if (DATE_COLUMN_NAMES.has(key)) {
          const formatted = formatDateCell(value)
          if (formatted) return [key, formatted] as [string, unknown]
        }
        return [key, cellText(value) || '-'] as [string, unknown]
      })
  }, [data])

  const equipmentName = record
    ? String(record['设备名称'] ?? record['设备信息'] ?? '')
    : ''
  const calibration = data?.calibration

  return (
    <Drawer
      open={open}
      title={`仪器档案${equipmentName ? `：${equipmentName}` : ''}`}
      size={960}
      onClose={onClose}
      destroyOnHidden
    >
      {isLoading && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin />
        </div>
      )}
      {error && <Alert type="error" showIcon title={error.message} />}
      {data && (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Descriptions
            bordered
            size="small"
            column={2}
            title={`基本信息（编号 ${data.matched_code || '-'}）`}
            styles={{ label: { width: 140 } }}
          >
            {equipmentEntries.map(([key, value]) => (
              <Descriptions.Item key={key} label={key}>
                {String(value)}
              </Descriptions.Item>
            ))}
          </Descriptions>
          {!data.matched_code && (
            <Alert
              type="warning"
              showIcon
              title="该设备没有填写设备编号，无法按编号匹配维保/维修/校验记录"
            />
          )}
          <Tabs
            items={[
              {
                key: 'maintenance',
                label: `维护保养（${data.maintenance.length}）`,
                children: <ProfileSectionTable rows={data.maintenance} />,
              },
              {
                key: 'repairs',
                label: `维修记录（${data.repairs.length}）`,
                children: <ProfileSectionTable rows={data.repairs} />,
              },
              {
                key: 'calibration',
                label: `校验情况（${calibration ? calibration.internal_summary.length + calibration.internal_plan.length + calibration.external.length : 0}）`,
                children: (
                  <Space direction="vertical" size={16} style={{ width: '100%' }}>
                    <div>
                      <Text strong>内校汇总（{calibration?.internal_summary.length ?? 0}）</Text>
                      <div style={{ marginTop: 8 }}>
                        <ProfileSectionTable rows={calibration?.internal_summary ?? []} />
                      </div>
                    </div>
                    <div>
                      <Text strong>内部校验计划（{calibration?.internal_plan.length ?? 0}）</Text>
                      <div style={{ marginTop: 8 }}>
                        <ProfileSectionTable rows={calibration?.internal_plan ?? []} />
                      </div>
                    </div>
                    <div>
                      <Text strong>外部校准、检定（{calibration?.external.length ?? 0}）</Text>
                      <div style={{ marginTop: 8 }}>
                        <ProfileSectionTable rows={calibration?.external ?? []} />
                      </div>
                    </div>
                  </Space>
                ),
              },
              {
                key: 'contracts',
                label: `维保合同（${data.contracts.length}）`,
                children: (
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Text type="secondary">
                      仅展示「涉及仪器及编号」包含设备编号 {data.matched_code || '-'} 的合同；合同共
                      {data.contracts_total} 份。
                    </Text>
                    <ProfileSectionTable rows={data.contracts} />
                  </Space>
                ),
              },
            ]}
          />
        </Space>
      )}
    </Drawer>
  )
}