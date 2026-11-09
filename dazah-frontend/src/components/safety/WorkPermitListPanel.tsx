'use client'

/**
 * 8 大特殊作业票列表面板：统计卡 + 筛选 + 服务端分页表格 + 新建抽屉。
 * 编号列为 next/link 跳详情页；待我审批数展示在统计卡。
 */

import {
  WORK_PERMITS_PAGE_KEY,
} from '@/lib/work-permit-api'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Divider,
  Drawer,
  Form,
  Input,
  message,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'

import {
  getApproverConfigs,
  getWorkPermitMeta,
  getWorkPermitSettings,
  getWorkPermitStats,
  getWorkPermits,
  updateWorkPermitSettings,
  upsertApproverConfig,
} from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { WorkPermitFormDrawer } from './WorkPermitFormDrawer'
import {
  permitLevelLabel,
  permitStatusLabel,
  permitTypeLabel,
} from './workPermitConstants'

type WorkPermitListItem = {
  id: string
  permit_no: string
  permit_type: string
  permit_level: string
  status: string
  apply_department: string | null
  work_description: string | null
  work_location: string | null
  planned_start_time: string | null
  planned_end_time: string | null
}

type WorkPermitStatsShape = {
  total: number
  draft: number
  pending_approval: number
  approved: number
  active: number
  completed: number
  rejected: number
  my_pending_approvals: number
}

type MetaShape = {
  permit_types: { value: string; label: string; no_prefix: string }[]
  level_options: Record<string, { value: string; label: string }[]>
  nodes?: Record<
    string,
    { key: string; name: string; kind: string; levels: string[] | null }[]
  >
}

const PAGE_SIZE = 20

export function WorkPermitListPanel({
  initialList,
  initialStats,
  initialError,
}: {
  initialList: {
    items: WorkPermitListItem[]
    total: number
  } | null
  initialStats: WorkPermitStatsShape | null
  initialError: string | null
}) {
  const permissions = usePagePermissions(WORK_PERMITS_PAGE_KEY)
  const [items, setItems] = useState<WorkPermitListItem[]>(
    initialList?.items ?? []
  )
  const [total, setTotal] = useState(initialList?.total ?? 0)
  const [stats, setStats] = useState<WorkPermitStatsShape | null>(
    initialStats
  )
  const [error, setError] = useState<string | null>(initialError)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [permitType, setPermitType] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [keyword, setKeyword] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [meta, setMeta] = useState<MetaShape | null>(null)
  const [configOpen, setConfigOpen] = useState(false)
  const [configType, setConfigType] = useState<string>('blind_plate')
  const [userOptions, setUserOptions] = useState<
    { value: string; label: string }[]
  >([])
  const [configMap, setConfigMap] = useState<Record<string, string>>({})
  const [certStrict, setCertStrict] = useState(false)

  const searchConfigUsers = useCallback(async (keyword: string) => {
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

  const openConfig = useCallback(async () => {
    setConfigOpen(true)
    const [configsRes, settingsRes] = await Promise.all([
      getApproverConfigs(),
      getWorkPermitSettings(),
    ])
    if (configsRes.code === 200 && configsRes.data) {
      const map: Record<string, string> = {}
      for (const item of configsRes.data.items) {
        if (item.permit_type === configType && item.approver_user_id) {
          map[item.node_key] = item.approver_user_id
        }
      }
      setConfigMap(map)
    }
    if (settingsRes.code === 200 && settingsRes.data) {
      setCertStrict(Boolean(settingsRes.data.cert_check_strict))
    }
  }, [configType])

  const toggleCertStrict = useCallback(async (checked: boolean) => {
    setCertStrict(checked)
    const response = await updateWorkPermitSettings(checked)
    if (response.code === 200) {
      message.success(checked ? '已开启证件强校验' : '已改为软提示')
    } else {
      setCertStrict(!checked)
      message.error(response.message ?? '保存失败')
    }
  }, [])

  const load = useCallback(
    async (
      targetPage = page,
      overrides?: { status?: string | null }
    ) => {
      setLoading(true)
      const nextStatus = overrides?.status !== undefined ? overrides.status : status
      const [listRes, statsRes] = await Promise.all([
        getWorkPermits({
          pageKey: WORK_PERMITS_PAGE_KEY,
          page: targetPage,
          pageSize: PAGE_SIZE,
          permitType,
          status: nextStatus,
          keyword,
        }),
        getWorkPermitStats(WORK_PERMITS_PAGE_KEY),
      ])
      if (listRes.code === 200 && listRes.data) {
        setItems(listRes.data.items as never)
        setTotal(listRes.data.total)
        setError(null)
      } else {
        setError(listRes.message ?? '加载失败')
      }
      if (statsRes.code === 200 && statsRes.data) {
        setStats(statsRes.data)
      }
      setLoading(false)
    },
    [page, permitType, status, keyword]
  )

  useEffect(() => {
    if (!initialList) {
      const timer = setTimeout(() => void load(1), 0)
      return () => clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void getWorkPermitMeta(WORK_PERMITS_PAGE_KEY).then((res) => {
      if (res.code === 200 && res.data) setMeta(res.data as never)
    })
  }, [])

  const columns: ColumnsType<WorkPermitListItem> = useMemo(
    () => [
      {
        title: '编号',
        dataIndex: 'permit_no',
        width: 170,
        render: (value: string, record) => (
          <Link href={`/safety/work-permits/${record.id}`}>{value}</Link>
        ),
      },
      {
        title: '票种',
        dataIndex: 'permit_type',
        width: 120,
        render: (value: string) => permitTypeLabel(value),
      },
      {
        title: '级别',
        dataIndex: 'permit_level',
        width: 90,
        render: (value: string) => permitLevelLabel(value),
      },
      {
        title: '状态',
        dataIndex: 'status',
        width: 90,
        render: (value: string) => {
          const colorMap: Record<string, string> = {
            draft: 'default',
            pending_approval: 'processing',
            approved: 'cyan',
            active: 'green',
            completed: 'purple',
            rejected: 'red',
            cancelled: 'default',
          }
          return <Tag color={colorMap[value] ?? 'default'}>{permitStatusLabel(value)}</Tag>
        },
      },
      {
        title: '申请单位',
        dataIndex: 'apply_department',
        width: 110,
        render: (value: string | null) => value ?? '-',
      },
      {
        title: '作业内容',
        dataIndex: 'work_description',
        width: 150,
        ellipsis: true,
        render: (value: string | null) => value ?? '-',
      },
      {
        title: '作业地点',
        dataIndex: 'work_location',
        width: 120,
        ellipsis: true,
        render: (value: string | null) => value ?? '-',
      },
      {
        title: '操作',
        key: 'actions',
        width: 80,
        render: (_, record) => (
          <Link href={`/safety/work-permits/${record.id}`}>详情</Link>
        ),
      },
    ],
    []
  )

  const handleCreated = useCallback(
    async () => {
      setDrawerOpen(false)
      setPage(1)
      await load(1)
    },
    [load]
  )

  const statCards: { label: string; value: number; status?: string }[] = [
    { label: '全部', value: stats?.total ?? 0 },
    { label: '待我审批', value: stats?.my_pending_approvals ?? 0, status: 'pending_approval' },
    { label: '审批中', value: stats?.pending_approval ?? 0, status: 'pending_approval' },
    { label: '作业中', value: stats?.active ?? 0, status: 'active' },
    { label: '已完工', value: stats?.completed ?? 0, status: 'completed' },
    { label: '已驳回', value: stats?.rejected ?? 0, status: 'rejected' },
  ]

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      {!permissions.canAccess && (
        <PlatformNotice
          type="warning"
          message="无权访问作业票审批页面"
          description="请联系管理员在系统设置中为你授予「作业票审批」页面权限。"
        />
      )}
      {error && (
        <PlatformNotice
          type="error"
          message="作业票列表加载失败"
          description={error}
          action={<Button size="small" onClick={() => void load(page)}>重试</Button>}
        />
      )}
      <Card size="small">
        <Space wrap size={16}>
          {statCards.map((card) => (
            <Button
              key={card.label}
              type={card.status && status === card.status ? 'primary' : 'default'}
              onClick={() => {
                setStatus(card.status ?? null)
                setPage(1)
                void load(1, { status: card.status ?? null })
              }}
            >
              {card.label}：{card.value}
            </Button>
          ))}
        </Space>
      </Card>
      <Card size="small">
        <Space wrap>
          <Select
            allowClear
            placeholder="票种"
            style={{ width: 150 }}
            value={permitType}
            options={(meta?.permit_types ?? []).map((item) => ({
              value: item.value,
              label: item.label,
            }))}
            onChange={(value) => {
              setPermitType(value ?? null)
              setPage(1)
            }}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 130 }}
            value={status}
            options={Object.entries(
              {
                draft: '草稿',
                pending_approval: '审批中',
                approved: '已批准',
                active: '作业中',
                completed: '已完工',
                rejected: '已驳回',
                cancelled: '已作废',
              }
            ).map(([value, label]) => ({ value, label }))}
            onChange={(value) => {
              setStatus(value ?? null)
              setPage(1)
            }}
          />
          <Input.Search
            allowClear
            placeholder="编号/内容/地点/单位"
            style={{ width: 240 }}
            onSearch={(value) => {
              setKeyword(value || null)
              setPage(1)
              void load(1)
            }}
          />
          <Button onClick={() => void load(page)}>刷新</Button>
          {permissions.canOperate && (
            <>
              <Button
                type="primary"
                onClick={() => setDrawerOpen(true)}
                disabled={!permissions.canAccess}
              >
                新建作业票
              </Button>
              <Button onClick={() => void openConfig()}>默认审批人配置</Button>
            </>
          )}
        </Space>
      </Card>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showSizeChanger: false,
          showTotal: (value) => `共 ${value} 条`,
          onChange: (next) => {
            setPage(next)
            void load(next)
          },
        }}
        scroll={{ x: 'max-content' }}
      />
      <WorkPermitFormDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onCreated={() => void handleCreated()}
      />
      <Drawer
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        size={560}
        destroyOnHidden
        title="节点默认审批人配置（提交时自动带出，可改派）"
      >
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Select
            style={{ width: 200 }}
            value={configType}
            options={(meta?.permit_types ?? []).map((item) => ({
              value: item.value,
              label: item.label,
            }))}
            onChange={(value) => {
              setConfigType(value)
              setConfigMap({})
              void openConfig()
            }}
          />
          {(meta?.nodes?.[configType] ?? [])
            .filter((node) => node.kind === 'approve')
            .map((node) => (
              <Form layout="vertical" key={node.key}>
                <Form.Item label={node.name}>
                  <Select
                    showSearch
                    allowClear
                    optionFilterProp="label"
                    style={{ width: '100%' }}
                    placeholder="搜索并选择默认审批人"
                    value={configMap[node.key] ?? undefined}
                    options={userOptions}
                    onSearch={(keyword) => void searchConfigUsers(keyword)}
                    filterOption={false}
                    notFoundContent={null}
                    onChange={async (value) => {
                      const response = await upsertApproverConfig({
                        permit_type: configType,
                        node_key: node.key,
                        approver_user_id: (value as string) ?? null,
                      })
                      if (response.code === 200) {
                        message.success('已保存')
                        setConfigMap((current) => ({
                          ...current,
                          [node.key]: (value as string) ?? '',
                        }))
                      } else {
                        message.error(response.message ?? '保存失败')
                      }
                    }}
                  />
                </Form.Item>
              </Form>
            ))}
          <Typography.Text type="secondary">
            按票种逐节点配置；提交作业票时自动带出，提交人可临时改派，管理员可改派未签字节点。
          </Typography.Text>
          <Divider style={{ margin: '4px 0' }} />
          <Form layout="vertical">
            <Form.Item label="作业人员证件强校验" style={{ marginBottom: 4 }}>
              <Switch
                checked={certStrict}
                onChange={(checked) => void toggleCertStrict(checked)}
              />
            </Form.Item>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              关闭时提交仅提示证件问题（缺证/类别不符/过期/持有人不符）；
              开启后存在问题时将拦截提交。
            </Typography.Text>
          </Form>
        </Space>
      </Drawer>
      {!meta && (
        <Typography.Text type="secondary">
          票种模板加载中…
        </Typography.Text>
      )}
    </Space>
  )
}

export type { WorkPermitListItem, WorkPermitStatsShape }
