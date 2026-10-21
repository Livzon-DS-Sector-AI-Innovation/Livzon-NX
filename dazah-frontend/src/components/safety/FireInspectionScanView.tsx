'use client'

import { useMemo, useState } from 'react'
import {
  Button,
  Card,
  Input,
  Segmented,
  Tag,
  Typography,
  message,
} from 'antd'
import { CheckCircleFilled, CloseCircleFilled } from '@ant-design/icons'
import dayjs from 'dayjs'

import PlatformNotice from '@/components/shared/PlatformNotice'
import { submitFireEquipmentInspection } from '@/actions/safety'
import { displayFieldText } from '@/lib/safety-page-tables'
import type { components } from '@/types/generated/schema'

const { Text, Title } = Typography

type FireEquipmentDetail = components['schemas']['FireEquipmentDetailResponse']
type ChecklistItem = components['schemas']['ChecklistItem']
type FireInspectionRecordItem =
  components['schemas']['FireInspectionRecordItem']

interface Props {
  pageKey: string
  inspectorName: string
  detail: FireEquipmentDetail | null
  error: string | null
}

const RESULT_TAG: Record<string, { color: string; label: string }> = {
  pass: { color: 'success', label: '合格' },
  fail: { color: 'error', label: '不合格' },
}

/**
 * 扫码点检视图（手机端）：器材信息 + 检查卡逐项点检 + 提交与历史。
 * 检查项默认「合格」，任一项不合格时需填写异常处理措施（与点检卡口径一致）。
 */
export default function FireInspectionScanView({
  pageKey,
  inspectorName,
  detail,
  error,
}: Props) {
  const equipment = detail?.equipment
  const checklist: ChecklistItem[] = useMemo(
    () => detail?.checklist ?? [],
    [detail]
  )
  const [results, setResults] = useState<Record<string, 'ok' | 'fail'>>({})
  const [remarks, setRemarks] = useState<Record<string, string>>({})
  const [abnormalAction, setAbnormalAction] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [history, setHistory] = useState<FireInspectionRecordItem[]>(
    detail?.recent_inspections ?? []
  )
  const [permissionDenied, setPermissionDenied] = useState(false)

  const failedKeys = useMemo(
    () =>
      checklist
        .filter((item) => (results[item.key] ?? 'ok') === 'fail')
        .map((item) => item.key),
    [checklist, results]
  )
  const hasFail = failedKeys.length > 0
  const bitableFields = useMemo(
    () =>
      Object.entries(equipment?.fields ?? {}).filter(
        ([, value]) => displayFieldText(value) !== ''
      ),
    [equipment]
  )
  const expiryTag = useMemo(() => {
    const days = equipment?.expiry_days_left
    if (days === null || days === undefined) return null
    if (days < 0) {
      return (
        <Tag color="error">有效期已过期{-days}天，请立即停用并更换</Tag>
      )
    }
    if (equipment?.expiry_status === 'expiring') {
      return <Tag color="warning">有效期仅剩{days}天，请安排更换</Tag>
    }
    return null
  }, [equipment])

  if (error) {
    return (
      <PlatformNotice
        type="error"
        message="器材信息加载失败"
        description={error}
        showRulesLink={false}
      />
    )
  }
  if (!equipment) {
    return (
      <PlatformNotice
        type="warning"
        message="未找到器材"
        description="二维码对应的器材可能已从飞书台账移除，请联系安全管理员确认。"
        showRulesLink={false}
      />
    )
  }

  const resultOf = (key: string): 'ok' | 'fail' => results[key] ?? 'ok'

  const handleSubmit = async () => {
    if (hasFail && !abnormalAction.trim()) {
      message.warning('存在不合格项，请填写异常处理措施')
      return
    }
    setSubmitting(true)
    try {
      const res = await submitFireEquipmentInspection({
        pageKey,
        equipmentId: String(equipment.id),
        data: {
          items: checklist.map((item) => ({
            key: item.key,
            result: resultOf(item.key),
            remark: remarks[item.key]?.trim() || null,
          })),
          abnormal_action: abnormalAction.trim() || null,
          source: 'scan',
        },
      })
      if (res.code === 200 && res.data) {
        message.success('点检提交成功')
        setHistory((prev) => [res.data as FireInspectionRecordItem, ...prev])
        setResults({})
        setRemarks({})
        setAbnormalAction('')
      } else if (res.code === 403) {
        setPermissionDenied(true)
        message.error('当前账号没有点检提交权限')
      } else {
        message.error(res.message || '点检提交失败，请稍后重试')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ maxWidth: 640, margin: '0 auto', display: 'grid', gap: 12 }}>
      <Card size="small">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Title level={4} style={{ margin: 0 }}>
            {equipment.equipment_type_label}点检
          </Title>
          <Tag color="processing">{equipment.equipment_no || '（未填编号）'}</Tag>
          {equipment.last_inspected_at ? (
            <Tag color={RESULT_TAG[equipment.last_inspection_result ?? '']?.color ?? 'default'}>
              上次：{dayjs(equipment.last_inspected_at).format('MM-DD HH:mm')}
              {' '}
              {RESULT_TAG[equipment.last_inspection_result ?? '']?.label ?? ''}
            </Tag>
          ) : (
            <Tag>首次点检</Tag>
          )}
        </div>
        {expiryTag ? <div style={{ marginTop: 8 }}>{expiryTag}</div> : null}
        <div style={{ marginTop: 8 }}>
          <Text>部门：{equipment.department || '—'}</Text>
          <br />
          <Text>位置：{equipment.location || '—'}</Text>
          <br />
          {equipment.expiry_date ? (
            <>
              <Text>有效期至：{String(equipment.expiry_date).slice(0, 10)}</Text>
              <br />
            </>
          ) : null}
          <Text type="secondary">检查要求：每月检查一次；点检人：{inspectorName || '当前用户'}</Text>
        </div>
      </Card>

      {bitableFields.length > 0 ? (
        <Card size="small" title="器材信息（多维表格）">
          <div style={{ display: 'grid', gap: 4 }}>
            {bitableFields.map(([name, value]) => (
              <div key={name} style={{ display: 'flex', gap: 8 }}>
                <Text type="secondary" style={{ minWidth: 110 }}>
                  {name}
                </Text>
                <Text style={{ flex: 1 }}>{displayFieldText(value)}</Text>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      <Card size="small" title="检查项目（逐项确认）">
        <div style={{ display: 'grid', gap: 12 }}>
          {checklist.map((item, index) => {
            const failed = resultOf(item.key) === 'fail'
            return (
              <div
                key={item.key}
                style={{
                  border: `1px solid ${failed ? 'var(--color-error-border, #ffa39e)' : 'var(--color-hairline-soft)'}`,
                  borderRadius: 8,
                  padding: 12,
                }}
              >
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <span>{index + 1}.</span>
                  <Text style={{ flex: 1 }}>{item.label}</Text>
                  <Segmented
                    value={resultOf(item.key)}
                    onChange={(value) =>
                      setResults((prev) => ({
                        ...prev,
                        [item.key]: value === 'fail' ? 'fail' : 'ok',
                      }))
                    }
                    options={[
                      { label: '合格', value: 'ok' },
                      { label: '不合格', value: 'fail' },
                    ]}
                  />
                </div>
                {failed ? (
                  <Input
                    placeholder="该不合格项备注（选填）"
                    size="small"
                    style={{ marginTop: 8 }}
                    value={remarks[item.key] ?? ''}
                    onChange={(event) =>
                      setRemarks((prev) => ({ ...prev, [item.key]: event.target.value }))
                    }
                  />
                ) : null}
              </div>
            )
          })}
        </div>
        <div style={{ marginTop: 8 }}>
          <Text type="secondary">
            <CheckCircleFilled style={{ color: '#52c41a' }} /> 合格 /{' '}
            <CloseCircleFilled style={{ color: '#ff4d4f' }} /> 不合格，全部合格即可提交
          </Text>
        </div>
      </Card>

      {hasFail ? (
        <Card size="small" title="异常处理措施（必填）">
          <Input.TextArea
            rows={3}
            maxLength={500}
            showCount
            placeholder="填写本次不合格项的处理措施，如报修、更换、限期整改等"
            value={abnormalAction}
            onChange={(event) => setAbnormalAction(event.target.value)}
          />
        </Card>
      ) : null}

      {permissionDenied ? (
        <PlatformNotice
          type="warning"
          message="没有点检提交权限"
          description="当前账号对该页面只有查看权限，请联系管理员在「权限管理」中开通操作权限。"
          showRulesLink={false}
        />
      ) : (
        <Button
          type="primary"
          size="large"
          block
          loading={submitting}
          onClick={() => void handleSubmit()}
        >
          提交点检结果
        </Button>
      )}

      <Card size="small" title={`最近点检记录（${history.length}）`}>
        {history.length === 0 ? (
          <Text type="secondary">暂无点检记录</Text>
        ) : (
          <div style={{ display: 'grid', gap: 8 }}>
            {history.map((record) => (
              <div
                key={record.id}
                style={{ borderBottom: '1px solid var(--color-hairline-soft)', paddingBottom: 8 }}
              >
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <Text strong>{dayjs(record.inspected_at).format('YYYY-MM-DD HH:mm')}</Text>
                  <Tag color={RESULT_TAG[record.result]?.color ?? 'default'}>
                    {RESULT_TAG[record.result]?.label ?? record.result}
                  </Tag>
                  <Text type="secondary">{record.inspector_name || '—'}</Text>
                </div>
                {record.failed_items?.length ? (
                  <Text type="danger" style={{ display: 'block', marginTop: 2 }}>
                    不合格：{record.failed_items.map((item) => String(item.label)).join('；')}
                  </Text>
                ) : null}
                {record.abnormal_action ? (
                  <Text type="secondary" style={{ display: 'block' }}>
                    处理措施：{record.abnormal_action}
                  </Text>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
