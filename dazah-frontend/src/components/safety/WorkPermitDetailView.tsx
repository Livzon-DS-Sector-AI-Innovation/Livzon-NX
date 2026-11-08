'use client'

/**
 * 作业票详情视图：票面字段、逐级审批时间线（同意/驳回）、验票/完工、
 * 气体分析录入（动火/受限空间周期复检）、关联票据互链、人员证件链接与附件。
 */

import {
  WORK_PERMITS_PAGE_KEY,
} from '@/lib/work-permit-api'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Timeline,
  Typography,
} from 'antd'
import type { TableProps } from 'antd/es/table'
import dayjs from 'dayjs'

import {
  acceptWorkPermit,
  addWorkPermitGasAnalysis,
  addWorkPermitRelation,
  approveWorkPermitNode,
  cancelWorkPermit,
  getApproverConfigs,
  getWorkPermitMeta,
  getWorkPermits,
  rejectWorkPermitNode,
  submitWorkPermit,
  verifyWorkPermit,
} from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import PlatformNotice from '@/components/shared/PlatformNotice'
import {
  NODE_KIND_LABELS,
  permitLevelLabel,
  permitStatusLabel,
  permitTypeLabel,
} from './workPermitConstants'

type Person = {
  role: string
  name: string
  certificate_id?: string | null
  certificate_no?: string | null
  certificate_valid?: boolean | null
  certificate_status?: string | null
}

type NodeItem = {
  id: string
  round: number
  seq: number
  node_key: string
  node_name: string
  node_kind: string
  status: string
  assigned_approver_name: string | null
  acted_by_name: string | null
  acted_at: string | null
  opinion: string | null
}

type GasItem = {
  id: string
  phase: string
  sampled_at: string
  analysis_point: string | null
  items: { name?: string; standard?: string; value?: string }[]
  oxygen_value: string | null
  analyst_name: string | null
}

type RelationItem = {
  related_permit_id: string
  related_permit_no: string
  related_permit_type: string
  related_permit_status: string
}

type AttachmentItem = {
  id: string
  category: string
  file_name: string
  size_bytes: number
}

export type WorkPermitDetailShape = {
  id: string
  permit_no: string
  permit_type: string
  permit_level: string
  status: string
  apply_department: string | null
  apply_time: string | null
  work_description: string | null
  work_location: string | null
  work_unit: string | null
  planned_start_time: string | null
  planned_end_time: string | null
  actual_start_time: string | null
  actual_end_time: string | null
  persons: Person[]
  risk_identifications: string[]
  safety_measures: { key: string; status: string; fills?: Record<string, string> }[]
  type_data: Record<string, unknown>
  related_legacy_no_text: string | null
  approval_round: number
  current_node_seq: number
  reject_opinion: string | null
  remark: string | null
  nodes: NodeItem[]
  gas_analyses: GasItem[]
  relations: RelationItem[]
  attachments: AttachmentItem[]
  next_gas_due_at: string | null
  gas_overdue: boolean
}

type MeasureTemplate = { key: string; text: string; group?: string; fill_keys?: string[] }

function fmt(value: string | null): string {
  if (!value) return '-'
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}

const ROLE_LABELS: Record<string, string> = {
  work_leader: '作业负责人',
  worker: '作业人',
  guardian: '监护人',
  briefer: '安全交底人',
  briefer_receiver: '接受交底人',
  process_tech: '工艺技术人员',
  process_guardian: '工艺监护人',
  rigger: '吊装作业人',
  rigging_slacker: '司索人',
  crane_commander: '指挥人员',
  electricity_user: '用电人',
  wiring_person: '接线人',
  wiring_guardian: '接线监护人',
}

export function WorkPermitDetailView({ initialDetail }: { initialDetail: WorkPermitDetailShape }) {
  const permissions = usePagePermissions(WORK_PERMITS_PAGE_KEY)
  const [detail, setDetail] = useState(initialDetail)
  const [meta, setMeta] = useState<{
    measures: Record<string, MeasureTemplate[]>
    gas_types?: string[]
    gas_cycle_minutes?: Record<string, number>
    nodes?: Record<
      string,
      { key: string; name: string; kind: string; levels: string[] | null }[]
    >
  } | null>(null)
  const [rejectOpen, setRejectOpen] = useState<NodeItem | null>(null)
  const [rejectOpinion, setRejectOpinion] = useState('')
  const [acting, setActing] = useState(false)
  const [gasForm] = Form.useForm()
  const [relationOpen, setRelationOpen] = useState(false)
  const [relationOptions, setRelationOptions] = useState<{ value: string; label: string }[]>([])
  const [gasError, setGasError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    const { getWorkPermitDetail } = await import('@/actions/safety')
    const response = await getWorkPermitDetail(detail.id)
    if (response.code === 200 && response.data) {
      setDetail(response.data as unknown as WorkPermitDetailShape)
    }
  }, [detail.id])

  useEffect(() => {
    void getWorkPermitMeta(WORK_PERMITS_PAGE_KEY).then((res) => {
      if (res.code === 200 && res.data) setMeta(res.data as never)
    })
  }, [])

  const measures = meta?.measures?.[detail.permit_type] ?? []
  const currentNodes = detail.nodes.filter((node) => node.round === detail.approval_round)
  const gasCycle = meta?.gas_cycle_minutes?.[detail.permit_type]
  const isGasType = (meta?.gas_types ?? []).includes(detail.permit_type)

  const doAction = useCallback(
    async (action: () => Promise<{ code: number; message?: string }>, successText: string) => {
      setActing(true)
      const response = await action()
      setActing(false)
      if (response.code !== 200) {
        message.error(response.message ?? '操作失败')
        return
      }
      message.success(successText)
      await reload()
    },
    [reload]
  )

  const handleApprove = useCallback(
    (node: NodeItem) => {
      void doAction(
        () => approveWorkPermitNode(detail.id, node.id),
        `已签批「${node.node_name}」`
      )
    },
    [detail.id, doAction]
  )

  const handleReject = useCallback(async () => {
    if (!rejectOpen) return
    if (!rejectOpinion.trim()) {
      message.warning('请填写驳回意见')
      return
    }
    await doAction(
      () => rejectWorkPermitNode(detail.id, rejectOpen.id, rejectOpinion.trim()),
      '已驳回'
    )
    setRejectOpen(null)
    setRejectOpinion('')
  }, [rejectOpen, rejectOpinion, detail.id, doAction])

  const gasColumns: TableProps<GasItem>['columns'] = [
    {
      title: '阶段',
      dataIndex: 'phase',
      width: 100,
      render: (value: string) =>
        value === 'pre_work' ? '作业前分析' : '作业期间复检',
    },
    {
      title: '取样时间',
      dataIndex: 'sampled_at',
      width: 150,
      render: (value: string) => fmt(value),
    },
    { title: '分析部位', dataIndex: 'analysis_point', width: 120, render: (v: string | null) => v ?? '-' },
    {
      title: '分析项目',
      dataIndex: 'items',
      render: (items: GasItem['items']) =>
        (items ?? [])
          .map((item) => `${item.name ?? ''}：${item.value ?? '-'}（标准 ${item.standard ?? '-'}）`)
          .join('；') || '-',
    },
    { title: '氧气含量', dataIndex: 'oxygen_value', width: 90, render: (v: string | null) => v ?? '-' },
    { title: '分析人', dataIndex: 'analyst_name', width: 90, render: (v: string | null) => v ?? '-' },
  ]

  const openRelation = useCallback(async () => {
    const listResponse = await getWorkPermits({ pageSize: 200 })
    if (listResponse.code === 200 && listResponse.data) {
      setRelationOptions(
        listResponse.data.items
          .filter((item) => item.id !== detail.id)
          .map((item) => ({
            value: item.id as string,
            label: `${item.permit_no}（${permitTypeLabel(item.permit_type)}）`,
          }))
      )
    }
    setRelationOpen(true)
  }, [detail.id])

  const [relationTarget, setRelationTarget] = useState<string | null>(null)
  const [submitOpen, setSubmitOpen] = useState(false)
  const [userOptions, setUserOptions] = useState<
    { value: string; label: string }[]
  >([])
  const [assignments, setAssignments] = useState<
    Record<string, string | null>
  >({})
  const [defaultsMap, setDefaultsMap] = useState<Record<string, string>>({})

  const activeNodeTemplates = (
    meta?.nodes?.[detail.permit_type] ?? []
  ).filter(
    (node) =>
      node.kind === 'approve' &&
      (node.levels === null ||
        node.levels.includes(detail.permit_level)),
  )

  const searchUsers = useCallback(async (keyword: string) => {
    const params = new URLSearchParams({ limit: '50' })
    if (keyword.trim()) params.set('keyword', keyword)
    const response = await fetch(`/api/v1/identity/personnel?${params}`)
    if (response.ok) {
      const json = await response.json()
      setUserOptions(
        ((json.data?.items ?? []) as Record<string, unknown>[]).map((u) => ({
          value: String(u.id),
          label: `${String(u.name)} - ${String(u.department || '未知部门')}`,
        })),
      )
    }
  }, [])

  const openSubmit = useCallback(
    async () => {
      const [configsRes] = await Promise.all([
        getApproverConfigs(),
        searchUsers(''),
      ]);
    if (configsRes.code === 200 && configsRes.data) {
      const map: Record<string, string> = {}
      for (const item of configsRes.data.items) {
        if (item.permit_type === detail.permit_type && item.approver_user_id) {
          map[item.node_key] = item.approver_user_id
        }
      }
      setDefaultsMap(map)
    }
    setAssignments({})
    setSubmitOpen(true)
  }, [detail.permit_type, searchUsers])

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      {!permissions.canAccess && (
        <PlatformNotice
          type="warning"
          message="无权访问作业票审批页面"
          description="请联系管理员授予「作业票审批」页面权限。"
        />
      )}
      <Card
        title={
          <Space>
            <span>{detail.permit_no}</span>
            <Tag>{permitTypeLabel(detail.permit_type)}</Tag>
            <Tag>{permitLevelLabel(detail.permit_level)}</Tag>
            <Tag color="blue">{permitStatusLabel(detail.status)}</Tag>
            <Typography.Text type="secondary">
              第 {detail.approval_round || 1} 轮
            </Typography.Text>
          </Space>
        }
        extra={
          <Space>
            {['draft', 'rejected'].includes(detail.status) &&
              permissions.canOperate && (
                <Button
                  type="primary"
                  onClick={() => void openSubmit()}
                >
                  提交审批
                </Button>
              )}
            {detail.status === 'approved' && permissions.canOperate && (
              <Button
                type="primary"
                loading={acting}
                onClick={() => void doAction(() => verifyWorkPermit(detail.id), '验票完成，开工')}
              >
                作业前验票（开工）
              </Button>
            )}
            {(detail.status === 'active' || detail.status === 'approved') &&
              permissions.canOperate && (
                <Popconfirm
                  title="确认完工验收？"
                  description="验收后作业票进入「已完工」，不可再录入检测数据。"
                  onConfirm={() =>
                    void doAction(
                      () => acceptWorkPermit(detail.id, {}),
                      '完工验收完成'
                    )
                  }
                >
                  <Button loading={acting}>完工验收</Button>
                </Popconfirm>
              )}
            {['draft', 'pending_approval', 'approved', 'active'].includes(
              detail.status
            ) &&
              permissions.canOperate && (
                <Popconfirm
                  title="确认作废该作业票？"
                  description="作废后不可恢复。"
                  onConfirm={() => void doAction(() => cancelWorkPermit(detail.id), '已作废')}
                >
                  <Button danger disabled={!permissions.canAccess} loading={acting}>
                    作废
                  </Button>
                </Popconfirm>
              )}
          </Space>
        }
      >
        <Descriptions
          column={3}
          size="small"
          items={[
            { key: 'desc', label: '作业内容', children: detail.work_description ?? '-' },
            { key: 'loc', label: '作业地点', children: detail.work_location ?? '-' },
            { key: 'unit', label: '作业单位', children: detail.work_unit ?? '-' },
            { key: 'dept', label: '申请单位', children: detail.apply_department ?? '-' },
            { key: 'apply', label: '申请时间', children: fmt(detail.apply_time) },
            {
              key: 'plan',
              label: '实施时间',
              children: `${fmt(detail.planned_start_time)} ~ ${fmt(detail.planned_end_time)}`,
            },
            { key: 'start', label: '实际开工', children: fmt(detail.actual_start_time) },
            { key: 'end', label: '实际完工', children: fmt(detail.actual_end_time) },
          ]}
        />
        {detail.reject_opinion && detail.status === 'rejected' && (
          <Alert
            type="error"
            showIcon
            message={`驳回意见：${detail.reject_opinion}`}
            style={{ marginTop: 12 }}
          />
        )}
        {detail.gas_overdue && (
          <Alert
            type="warning"
            showIcon
            message={`气体复检已超期（下次要求：${fmt(detail.next_gas_due_at)}），请立即复检`}
            style={{ marginTop: 12 }}
          />
        )}
        {Object.keys(detail.type_data ?? {}).length > 0 && (
          <Descriptions
            style={{ marginTop: 12 }}
            column={3}
            size="small"
            items={Object.entries(detail.type_data).map(([key, value]) => ({
              key,
              label: key,
              children: String(value ?? '-'),
            }))}
          />
        )}
      </Card>

      <Card title="逐级审批（按票面签字顺序，任一节点驳回后需重新逐级签）">
        {currentNodes.length === 0 ? (
          <Typography.Text type="secondary">尚未提交审批</Typography.Text>
        ) : (
          <Timeline
            items={currentNodes.map((node) => ({
              color:
                node.status === 'approved'
                  ? 'green'
                  : node.status === 'pending'
                    ? 'blue'
                    : node.status === 'rejected'
                      ? 'red'
                      : 'gray',
              children: (
                <Space wrap>
                  <Typography.Text strong>{node.node_name}</Typography.Text>
                  <Tag>
                    {node.round}轮 · {NODE_KIND_LABELS[node.node_kind] ?? node.node_kind}
                  </Tag>
                  {node.assigned_approver_name && (
                    <Typography.Text type="secondary">
                      指派：{node.assigned_approver_name}
                    </Typography.Text>
                  )}
                  {node.status === 'approved' && (
                    <>
                      <Tag color="green">已签</Tag>
                      <Typography.Text type="secondary">
                        {node.acted_by_name} {fmt(node.acted_at)}
                      </Typography.Text>
                    </>
                  )}
                  {node.status === 'pending' && <Tag color="blue">待处理</Tag>}
                  {node.status === 'rejected' && <Tag color="red">已驳回</Tag>}
                  {node.opinion && (
                    <Typography.Text type="secondary">意见：{node.opinion}</Typography.Text>
                  )}
                  {node.status === 'pending' && permissions.canOperate && (
                    <>
                      <Button
                        size="small"
                        type="primary"
                        loading={acting}
                        onClick={() => handleApprove(node)}
                      >
                        同意
                      </Button>
                      <Button size="small" danger onClick={() => setRejectOpen(node)}>
                        驳回
                      </Button>
                    </>
                  )}
                </Space>
              ),
            }))}
          />
        )}
      </Card>

      <Card title="作业人员与证件（点击证件号跳转证件管理）">
        {(detail.persons ?? []).length === 0 ? (
          <Typography.Text type="secondary">未填写人员</Typography.Text>
        ) : (
          <Space wrap size={12}>
            {detail.persons.map((person, index) => (
              <Space key={`${person.role}-${index}`} size={4}>
                <Typography.Text>
                  {ROLE_LABELS[person.role] ?? person.role}：{person.name}
                </Typography.Text>
                {person.certificate_id ? (
                  <Link href={`/safety/work-certificates?cert=${person.certificate_id}`}>
                    证件 {person.certificate_no ?? '查看'}
                  </Link>
                ) : (
                  <Typography.Text type="warning">（未关联证件）</Typography.Text>
                )}
                {person.certificate_valid === false && (
                  <Tag color="red">
                    {person.certificate_status === 'expired' ? '证件已过期' : '证件异常'}
                  </Tag>
                )}
              </Space>
            ))}
          </Space>
        )}
        {detail.related_legacy_no_text && (
          <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
            关联票号（历史口径）：{detail.related_legacy_no_text}
          </Typography.Text>
        )}
        <div style={{ marginTop: 8 }}>
          <Space wrap>
            <span>结构化关联票据：</span>
            {(detail.relations ?? []).map((relation) => (
              <Link key={relation.related_permit_id} href={`/safety/work-permits/${relation.related_permit_id}`}>
                {relation.related_permit_no}
              </Link>
            ))}
            <Button size="small" onClick={() => void openRelation()}>
              添加关联票
            </Button>
          </Space>
        </div>
      </Card>

      <Card title="安全措施确认">
        {measures.length === 0 ? (
          <Typography.Text type="secondary">模板加载中…</Typography.Text>
        ) : (
          <Space orientation="vertical" size={4} style={{ display: 'flex' }}>
            {measures.map((measure) => {
              const filled = detail.safety_measures.find((item) => item.key === measure.key)
              return (
                <Space key={measure.key} wrap>
                  <Typography.Text style={{ maxWidth: 520 }}>
                    {measure.text}
                  </Typography.Text>
                  {filled?.status === 'yes' && <Tag color="green">是</Tag>}
                  {filled?.status === 'not_applicable' && <Tag>不适用</Tag>}
                  {!filled && <Tag color="default">未确认</Tag>}
                  {filled?.status === 'yes' &&
                    Object.entries(filled.fills ?? {})
                      .filter(([, value]) => value)
                      .map(([key, value]) => (
                        <Typography.Text key={key} type="secondary">
                          {key}={value}
                        </Typography.Text>
                      ))}
                </Space>
              )
            })}
          </Space>
        )}
        {(detail.risk_identifications ?? []).length > 0 && (
          <>
            <Typography.Title level={5} style={{ marginTop: 12 }}>
              风险辨识结果
            </Typography.Title>
            <Space wrap>
              {detail.risk_identifications.map((risk) => (
                <Tag key={risk}>{risk}</Tag>
              ))}
            </Space>
          </>
        )}
      </Card>

      {(isGasType || (detail.gas_analyses ?? []).length > 0) && (
        <Card
          title={
            <Space>
              气体分析记录
              {gasCycle && (
                <Typography.Text type="secondary">
                  复检间隔 {gasCycle} 分钟
                  {detail.status === 'active' &&
                    `（下次要求 ${fmt(detail.next_gas_due_at)}）`}
                </Typography.Text>
              )}
            </Space>
          }
        >
          <Table<GasItem>
            rowKey="id"
            size="small"
            columns={gasColumns}
            dataSource={detail.gas_analyses ?? []}
            pagination={false}
          />
          {detail.status === 'active' && permissions.canOperate && (
            <Form
              form={gasForm}
              layout="inline"
              style={{ marginTop: 12 }}
              onFinish={async (values) => {
                const response = await addWorkPermitGasAnalysis(detail.id, {
                  phase: 'on_duty',
                  sampled_at: values.sampled_at.toISOString(),
                  analysis_point: values.analysis_point ?? null,
                  items: [
                    {
                      name: values.gas_name ?? '可燃气体',
                      standard: values.standard ?? '0',
                      value: values.gas_value ?? null,
                    },
                  ],
                  analyst_name: values.analyst_name ?? null,
                })
                if (response.code !== 200) {
                  message.error(response.message ?? '录入失败')
                  return
                }
                message.success('复检记录已录入')
                gasForm.resetFields()
                setGasError(null)
                await reload()
              }}
            >
              {gasError && <Typography.Text type="danger">{gasError}</Typography.Text>}
              <Form.Item name="sampled_at" rules={[{ required: true, message: '选择时间' }]}>
                <DatePicker showTime placeholder="取样时间" />
              </Form.Item>
              <Form.Item name="analysis_point">
                <Input placeholder="分析部位" style={{ width: 120 }} />
              </Form.Item>
              <Form.Item name="gas_name" initialValue="可燃气体">
                <Input style={{ width: 110 }} />
              </Form.Item>
              <Form.Item name="gas_value">
                <Input placeholder="结果" style={{ width: 90 }} />
              </Form.Item>
              <Form.Item name="standard" initialValue="0">
                <Input placeholder="合格标准" style={{ width: 100 }} />
              </Form.Item>
              <Form.Item name="analyst_name">
                <Input placeholder="分析人" style={{ width: 100 }} />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit">
                  录入复检
                </Button>
              </Form.Item>
            </Form>
          )}
        </Card>
      )}

      {(detail.attachments ?? []).length > 0 && (
        <Card title="附件（盲板位置图/简图/示意图等）">
          <Space wrap>
            {detail.attachments.map((attachment) => (
              <a
                key={attachment.id}
                href={`/api/v1/safety/work-permits/${detail.id}/attachments/${attachment.id}/preview`}
                target="_blank"
                rel="noreferrer"
              >
                {attachment.file_name}
              </a>
            ))}
          </Space>
        </Card>
      )}

      <Modal
        open={Boolean(rejectOpen)}
        title={`驳回「${rejectOpen?.node_name ?? ''}」`}
        onCancel={() => setRejectOpen(null)}
        onOk={() => void handleReject()}
        confirmLoading={acting}
        okText="确认驳回"
        okButtonProps={{ danger: true }}
      >
        <Typography.Paragraph type="secondary">
          驳回后整票变为「已驳回」，申请人修改后重新提交，全部节点重新逐级签（历史轮次保留可追溯）。
        </Typography.Paragraph>
        <Input.TextArea
          rows={3}
          value={rejectOpinion}
          placeholder="驳回意见（必填）"
          onChange={(event) => setRejectOpinion(event.target.value)}
        />
      </Modal>

      <Modal
        open={submitOpen}
        title={`提交审批（第 ${detail.approval_round + 1} 轮，逐级签批）`}
        onCancel={() => setSubmitOpen(false)}
        confirmLoading={acting}
        okText="提交"
        okButtonProps={{
          disabled: activeNodeTemplates.some(
            (node) => !assignments[node.key] && !defaultsMap[node.key],
          ),
        }}
        onOk={async () => {
          setActing(true)
          const response = await submitWorkPermit(
            detail.id,
            activeNodeTemplates.map((node) => ({
              node_key: node.key,
              approver_user_id:
                assignments[node.key] ?? defaultsMap[node.key] ?? null,
            })),
          )
          setActing(false)
          if (response.code !== 200) {
            message.error(response.message ?? '提交失败')
            return
          }
          message.success('已提交审批')
          setSubmitOpen(false)
          const warnings = response.data?.warnings ?? []
          if (warnings.length > 0) {
            Modal.warning({
              title: '已提交，但人员证件存在以下提示',
              width: 520,
              content: (
                <ul style={{ paddingLeft: 18, margin: '8px 0 0' }}>
                  {warnings.map((item) => (
                    <li key={item} style={{ fontSize: 13 }}>{item}</li>
                  ))}
                </ul>
              ),
            })
          }
          await reload()
        }}
      >
        <Typography.Paragraph type="secondary">
          按「{permitTypeLabel(detail.permit_type)}
          （{permitLevelLabel(detail.permit_level)}）」级别激活的审批节点顺序逐级签批；
          可为每个节点搜索并指派审批人（留空使用默认配置）。
        </Typography.Paragraph>
        {activeNodeTemplates.length === 0 ? (
          <Typography.Text type="warning">
            该票种没有逐级审批节点，可直接验票开工。
          </Typography.Text>
        ) : (
          activeNodeTemplates.map((node) => (
            <Form layout="vertical" key={node.key}>
              <Form.Item label={node.name}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder={
                    defaultsMap[node.key]
                      ? `默认：${defaultsMap[node.key] === assignments[node.key] ? '' : '已配置，可改派'}`
                      : '搜索并选择审批人（必选）'
                  }
                  style={{ width: '100%' }}
                  value={assignments[node.key] ?? defaultsMap[node.key] ?? undefined}
                  options={userOptions}
                  onSearch={(keyword) => void searchUsers(keyword)}
                  filterOption={false}
                  notFoundContent={null}
                  onChange={(value) =>
                    setAssignments((current) => ({
                      ...current,
                      [node.key]: (value as string) ?? null,
                    }))
                  }
                />
              </Form.Item>
            </Form>
          ))
        )}
      </Modal>

      <Drawer
        open={relationOpen}
        onClose={() => setRelationOpen(false)}
        size={420}
        title="添加关联作业票"
        footer={
          <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button onClick={() => setRelationOpen(false)}>取消</Button>
            <Button
              type="primary"
              disabled={!relationTarget}
              onClick={async () => {
                if (!relationTarget) return
                await doAction(
                  () => addWorkPermitRelation(detail.id, relationTarget),
                  '关联已添加'
                )
                setRelationOpen(false)
                setRelationTarget(null)
              }}
            >
              关联
            </Button>
          </Space>
        }
      >
        <Select
          showSearch
          optionFilterProp="label"
          style={{ width: '100%' }}
          placeholder="选择要关联的作业票"
          value={relationTarget}
          options={relationOptions}
          onChange={(value) => setRelationTarget(value)}
        />
      </Drawer>
    </Space>
  )
}
