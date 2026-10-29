'use client'

import { useEffect, useState } from 'react'
import {
  Descriptions,
  Drawer,
  Empty,
  Spin,
  Tag,
  Typography,
} from 'antd'
import dayjs from 'dayjs'

import { getFireEquipmentDetail } from '@/actions/safety'
import type { components } from '@/types/generated/schema'

const { Text } = Typography

type FireEquipmentDetail = components['schemas']['FireEquipmentDetailResponse']
type FireInspectionRecordItem =
  components['schemas']['FireInspectionRecordItem']

interface Props {
  open: boolean
  pageKey: string
  equipmentId: string | null
  onClose: () => void
}

const RESULT_TAG: Record<string, { color: string; label: string }> = {
  pass: { color: 'success', label: '合格' },
  fail: { color: 'error', label: '不合格' },
}

function InspectionSummary({ record }: { record: FireInspectionRecordItem }) {
  const tag = RESULT_TAG[record.result] ?? { color: 'default', label: record.result }
  return (
    <div style={{ padding: '8px 0', borderBottom: '1px solid var(--color-hairline-soft)' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <Text strong>{dayjs(record.inspected_at).format('YYYY-MM-DD HH:mm')}</Text>
        <Tag color={tag.color}>{tag.label}</Tag>
        <Text type="secondary">点检人：{record.inspector_name || '—'}</Text>
        <Text type="secondary">
          来源：{record.source === 'scan' ? '扫码' : '网页'}
        </Text>
      </div>
      {record.failed_items?.length ? (
        <div style={{ marginTop: 4 }}>
          <Text type="danger">
            不合格项：{record.failed_items.map((item) => String(item.label)).join('；')}
          </Text>
        </div>
      ) : null}
      {record.abnormal_action ? (
        <div style={{ marginTop: 4 }}>
          <Text type="secondary">异常处理措施：{record.abnormal_action}</Text>
        </div>
      ) : null}
    </div>
  )
}

/** 抽屉内容：按 equipmentId 用 key 重挂载（state 随之重置），挂载后拉取详情。 */
function DrawerContent({
  pageKey,
  equipmentId,
}: {
  pageKey: string
  equipmentId: string
}) {
  const [detail, setDetail] = useState<FireEquipmentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getFireEquipmentDetail({
      pageKey,
      equipmentId,
    })
      .then((res) => {
        if (cancelled) return
        if (res.code === 200 && res.data) {
          setDetail(res.data)
        } else {
          setError(res.message || '读取器材详情失败')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [pageKey, equipmentId])

  const equipment = detail?.equipment

  return (
    <>
      {loading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin />
        </div>
      ) : error ? (
        <Empty description={error} />
      ) : equipment ? (
        <>
          <Descriptions
            column={2}
            size="small"
            bordered
            items={[
              { key: 'no', label: '器材编号', children: equipment.equipment_no || '（未填编号）' },
              { key: 'type', label: '类型', children: equipment.equipment_type_label },
              { key: 'dept', label: '归属部门', children: equipment.department || '—' },
              { key: 'loc', label: '存放位置', children: equipment.location || '—' },
              {
                key: 'tab',
                label: '来源子表',
                children: equipment.tab_name || '—',
                span: 2,
              },
              {
                key: 'last',
                label: '最近点检',
                span: 2,
                children: equipment.last_inspected_at
                  ? `${dayjs(equipment.last_inspected_at).format('YYYY-MM-DD HH:mm')}（${
                      RESULT_TAG[equipment.last_inspection_result ?? '']?.label ?? '—'
                    }）`
                  : '尚未点检',
              },
            ]}
          />
          <Typography.Title level={5} style={{ marginTop: 16 }}>
            台账字段（飞书多维表格）
          </Typography.Title>
          {Object.entries(equipment.fields ?? {}).length === 0 ? (
            <Empty description="无字段数据" />
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 4 }}>
              {Object.entries(equipment.fields ?? {}).map(([name, value]) => (
                <div key={name} style={{ display: 'flex', gap: 8 }}>
                  <Text type="secondary" style={{ minWidth: 120 }}>
                    {name}
                  </Text>
                  <Text style={{ flex: 1 }}>
                    {value === null || value === undefined || value === ''
                      ? '—'
                      : String(
                          typeof value === 'object'
                            ? JSON.stringify(value)
                            : value
                        )}
                  </Text>
                </div>
              ))}
            </div>
          )}
          <Typography.Title level={5} style={{ marginTop: 16 }}>
            最近点检记录
          </Typography.Title>
          {(detail?.recent_inspections ?? []).length === 0 ? (
            <Empty description="暂无点检记录" />
          ) : (
            (detail?.recent_inspections ?? []).map((record) => (
              <InspectionSummary key={record.id} record={record} />
            ))
          )}
        </>
      ) : (
        <Empty description="未找到器材" />
      )}
    </>
  )
}

/** 器材详情抽屉：基础信息 + 全部镜像字段 + 最近点检记录。 */
export default function FireEquipmentDetailDrawer({
  open,
  pageKey,
  equipmentId,
  onClose,
}: Props) {
  return (
    <Drawer
      title="器材详情"
      open={open}
      onClose={onClose}
      size={520}
      destroyOnHidden
    >
      {open && equipmentId ? (
        <DrawerContent key={equipmentId} pageKey={pageKey} equipmentId={equipmentId} />
      ) : null}
    </Drawer>
  )
}
