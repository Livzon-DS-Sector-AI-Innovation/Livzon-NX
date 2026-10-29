'use client'

// 设备模块飞书配置页：自建应用凭据管理与各车间多维表格链接。
// 应用先在此登记（App Secret 加密、永不回显明文），各车间配置时下拉选择
// 复用；编辑/测试/同步复用巡检镜像的既有接口。

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { HTMLAttributes } from 'react'
import {
  App, Button, Card, Form, Input, Modal, Popconfirm, Popover, Space, Spin,
  Table, Tag, Tooltip, Typography,
} from 'antd'
import Alert from '@/components/shared/PlatformNotice'
import {
  ApiOutlined, CheckCircleOutlined, CopyOutlined, DeleteOutlined,
  EditOutlined, LinkOutlined, PlusOutlined, SafetyCertificateOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEquipmentWorkshops } from '@/lib/equipment-workshop-registry'
import type {
  FeishuAppSummary,
  FeishuAppUpdateRequest,
  InspectionFeishuConfigDetail,
} from '@/types/inspection-feishu'
import {
  createFeishuApp,
  deleteFeishuApp,
  fetchFeishuApps,
  fetchInspectionFeishuConfigList,
  fetchInspectionFeishuSyncStatus,
  testInspectionFeishuConfig,
  triggerInspectionFeishuSync,
  updateFeishuApp,
} from '@/lib/api/inspection-feishu'
import { InspectionFeishuConfigDrawer } from './inspection/InspectionFeishuConfigDrawer'

const { Text, Paragraph } = Typography

interface WorkshopRow {
  code: string
  label: string
  detail: InspectionFeishuConfigDetail | null
  configured: boolean
}


interface SyncBrief {
  totalRows: number
  lastRun: string | null
  lastStatus: string | null
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  return dayjs(iso).format('MM-DD HH:mm')
}

export function FeishuConfigPage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [details, setDetails] = useState<InspectionFeishuConfigDetail[]>([])
  const [apps, setApps] = useState<FeishuAppSummary[]>([])
  const [syncBriefs, setSyncBriefs] = useState<Record<string, SyncBrief>>({})
  const [syncing, setSyncing] = useState<string | null>(null)
  const [testing, setTesting] = useState<string | null>(null)
  const [drawerWorkshop, setDrawerWorkshop] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [appModalOpen, setAppModalOpen] = useState(false)
  const [editingApp, setEditingApp] = useState<FeishuAppSummary | null>(null)
  const [appSubmitting, setAppSubmitting] = useState(false)
  const [deletingApp, setDeletingApp] = useState<string | null>(null)
  const [appForm] = Form.useForm()
  // 车间清单来自车间注册表接口（车间管理页维护），失败回落内置常量
  const workshops = useEquipmentWorkshops()

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const [list, appList] = await Promise.all([
        fetchInspectionFeishuConfigList(),
        fetchFeishuApps().catch(() => [] as FeishuAppSummary[]),
      ])
      setDetails(list)
      setApps(appList)
      const enabled = list.filter((d) => d.enabled)
      const briefs = await Promise.all(
        enabled.map(async (d) => {
          try {
            const status = await fetchInspectionFeishuSyncStatus(d.workshop_code)
            const tables = status.tables ?? []
            return [d.workshop_code, {
              totalRows: tables.reduce((sum, t) => sum + (t.total_rows || 0), 0),
              lastRun: tables.map((t) => t.last_run_at).filter(Boolean).sort().at(-1) ?? null,
              lastStatus: tables.some((t) => t.last_status === 'failed') ? 'failed' : null,
            } satisfies SyncBrief] as const
          } catch {
            return [d.workshop_code, { totalRows: 0, lastRun: null, lastStatus: null }] as const
          }
        }),
      )
      setSyncBriefs(Object.fromEntries(briefs))
    } catch (error) {
      setLoadError((error as Error).message || '加载飞书配置失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  const rows = useMemo<WorkshopRow[]>(() => {
    const byCode = new Map(details.map((d) => [d.workshop_code, d]))
    return workshops.map((ws) => {
      const detail = byCode.get(ws.code) ?? null
      return {
        code: ws.code,
        label: ws.name,
        detail,
        // 环境变量回退的默认车间无凭据/表格时同样视为未配置
        configured: Boolean(detail && detail.app_token && detail.app_id),
      }
    })
  }, [details, workshops])

  const openAppModal = useCallback((app: FeishuAppSummary | null) => {
    setEditingApp(app)
    setAppModalOpen(true)
    if (app) {
      appForm.setFieldsValue({ name: app.name, app_id: app.app_id, app_secret: '' })
    } else {
      appForm.resetFields()
    }
  }, [appForm])

  const submitApp = useCallback(async () => {
    const values = await appForm.validateFields()
    setAppSubmitting(true)
    try {
      if (editingApp) {
        const payload: FeishuAppUpdateRequest = { name: values.name.trim() }
        const secret = (values.app_secret || '').trim()
        if (secret) payload.app_secret = secret
        await updateFeishuApp(editingApp.id, payload)
        message.success('应用已更新')
      } else {
        await createFeishuApp({
          name: values.name.trim(),
          app_id: values.app_id.trim(),
          app_secret: values.app_secret.trim(),
        })
        message.success('应用已登记，配置车间时可直接下拉选择')
      }
      setAppModalOpen(false)
      setReloadKey((k) => k + 1)
    } catch (error) {
      message.error((error as Error).message || '保存应用失败')
    } finally {
      setAppSubmitting(false)
    }
  }, [appForm, editingApp, message])

  const removeApp = useCallback(async (app: FeishuAppSummary) => {
    setDeletingApp(app.id)
    try {
      await deleteFeishuApp(app.id)
      message.success('应用已删除')
      setReloadKey((k) => k + 1)
    } catch (error) {
      message.error((error as Error).message || '删除应用失败')
    } finally {
      setDeletingApp(null)
    }
  }, [message])

  const copy = useCallback(async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      message.success(`已复制${label}`)
    } catch {
      message.error('复制失败，请手动选择复制')
    }
  }, [message])

  const handleSync = useCallback(async (workshop: string) => {
    setSyncing(workshop)
    try {
      const results = await triggerInspectionFeishuSync(workshop)
      const errors = Object.entries(results).filter(([, v]) => v.error)
      if (errors.length > 0) {
        message.warning(`同步完成，${errors.length} 张表失败：${errors.map(([k]) => k).join('、')}`)
      } else {
        const synced = Object.values(results).reduce((sum, v) => sum + (v.synced || 0), 0)
        message.success(`飞书同步完成，本次更新 ${synced} 条`)
      }
      setReloadKey((k) => k + 1)
    } catch (error) {
      message.error((error as Error).message || '同步失败')
    } finally {
      setSyncing(null)
    }
  }, [message])

  const handleTest = useCallback(async (workshop: string) => {
    setTesting(workshop)
    try {
      const result = await testInspectionFeishuConfig(workshop)
      if (result.success) {
        message.success(`连接正常，读取到 ${result.table_count} 张子表`)
      } else {
        message.warning(result.message || '连接测试失败')
      }
      setReloadKey((k) => k + 1)
    } catch (error) {
      message.error((error as Error).message || '连接测试失败')
    } finally {
      setTesting(null)
    }
  }, [message])

  const columns: ColumnsType<WorkshopRow> = [
    {
      title: '车间', dataIndex: 'label', width: 110,
      render: (label: string, row) => (
        <div>
          <Text strong>{label}</Text>
          <div style={{ fontSize: 12, color: '#787671' }}>{row.code}</div>
        </div>
      ),
    },
    {
      title: '状态', width: 92,
      render: (_, row) => {
        if (!row.configured) return <Tag>未配置</Tag>
        if (!row.detail?.enabled) return <Tag color="orange">已停用</Tag>
        return <Tag color="green" icon={<CheckCircleOutlined />}>启用</Tag>
      },
    },
    {
      title: 'App ID', width: 160,
      render: (_, row) => row.detail?.app_id ? (
        <Space size={4}>
          <Text code style={{ fontSize: 12 }}>{row.detail.app_id}</Text>
          <Button
            type="text" size="small" icon={<CopyOutlined />}
            aria-label={`复制 App ID ${row.code}`}
            onClick={() => void copy(row.detail!.app_id, 'App ID')}
          />
        </Space>
      ) : '-',
    },
    {
      title: '多维表格', width: 150,
      render: (_, row) => {
        const url = row.detail?.base_url
        if (!row.configured) return '-'
        if (!url) {
          return (
            <Tooltip title="配置时粘贴完整链接后可在此直达">
              <Text type="secondary" style={{ fontSize: 12 }}>未存链接</Text>
            </Tooltip>
          )
        }
        return (
          <Space size={4}>
            <a href={url} target="_blank" rel="noreferrer">
              <Button size="small" icon={<LinkOutlined />}>打开</Button>
            </a>
            <Button
              type="text" size="small" icon={<CopyOutlined />}
              aria-label={`复制多维表格链接 ${row.code}`}
              onClick={() => void copy(url, '多维表格链接')}
            />
          </Space>
        )
      },
    },
    {
      title: '数据表', width: 210,
      render: (_, row) => {
        const d = row.detail
        if (!row.configured || !d) return '-'
        const tables = [
          { name: '今日巡检', id: d.today_table_id },
          { name: '历史记录', id: d.history_table_id },
          { name: '设备档案', id: d.device_table_id },
        ]
        return (
          <Space size={12} wrap>
            {tables.map((t) => (
              <Popover
                key={t.name}
                content={<Text code style={{ fontSize: 12 }}>{t.id || '未配置'}</Text>}
                title={`${t.name} Table ID`}
              >
                <Button
                  type="text" size="small"
                  onClick={() => t.id && void copy(t.id, `${t.name} Table ID`)}
                >
                  {t.name}
                </Button>
              </Popover>
            ))}
          </Space>
        )
      },
    },
    {
      title: '镜像 / 最近同步', width: 150,
      render: (_, row) => {
        if (!row.configured) return '-'
        const brief = syncBriefs[row.code]
        if (!brief) return <Text type="secondary" style={{ fontSize: 12 }}>暂无状态</Text>
        return (
          <div style={{ fontSize: 12, color: '#787671' }}>
            <div>
              镜像 {brief.totalRows} 行
              {brief.lastStatus === 'failed' && (
                <Text type="danger" style={{ fontSize: 12 }}> · 同步失败</Text>
              )}
            </div>
            <div>{fmtTime(brief.lastRun)}</div>
          </div>
        )
      },
    },
    {
      title: '操作', width: 200, fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <Button size="small" onClick={() => setDrawerWorkshop(row.code)}>
            {row.configured ? '编辑' : '配置'}
          </Button>
          {row.configured && (
            <>
              <Button
                size="small" icon={<SyncOutlined spin={syncing === row.code} />}
                loading={syncing === row.code}
                onClick={() => void handleSync(row.code)}
              >
                同步
              </Button>
              <Button
                size="small" icon={<SafetyCertificateOutlined />}
                loading={testing === row.code}
                onClick={() => void handleTest(row.code)}
              >
                测试
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ]

  // 应用列表列宽固定，长名称省略号截断，各行列位置严格对齐
  const appColumns: ColumnsType<FeishuAppSummary> = [
    {
      title: '应用名称', dataIndex: 'name', width: 200, ellipsis: true,
      render: (name: string) => <Text strong>{name}</Text>,
    },
    {
      title: 'App ID', dataIndex: 'app_id', width: 210,
      render: (appId: string, app) => (
        <Space size={4}>
          <Text code style={{ fontSize: 12 }}>{appId}</Text>
          <Button
            type="text" size="small" icon={<CopyOutlined />}
            aria-label={`复制 App ID ${app.name}`}
            onClick={() => void copy(appId, 'App ID')}
          />
        </Space>
      ),
    },
    {
      title: 'App Secret', dataIndex: 'app_secret_configured', width: 280,
      render: (_, app) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {app.app_secret_configured
            ? `已配置（${app.app_secret_masked || '••••••'}），不回显明文`
            : '未配置'}
        </Text>
      ),
    },
    {
      title: '使用车间', dataIndex: 'in_use_workshops',
      render: (_, app) => (
        app.in_use_workshops.length > 0 ? (
          <Space size={4} wrap>
            {app.in_use_workshops.map((w) => <Tag key={w}>{w}</Tag>)}
          </Space>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>未使用</Text>
        )
      ),
    },
    {
      title: '操作', width: 140, fixed: 'right',
      render: (_, app) => (
        <Space size={4}>
          <Button
            size="small" icon={<EditOutlined />}
            aria-label={`编辑应用 ${app.name}`}
            onClick={() => openAppModal(app)}
          >
            编辑
          </Button>
          <Popconfirm
            title="删除该应用？"
            description="仍被车间配置引用时会删除失败"
            okText="删除"
            okButtonProps={{ danger: true }}
            onConfirm={() => void removeApp(app)}
          >
            <Button
              size="small" danger icon={<DeleteOutlined />}
              aria-label={`删除应用 ${app.name}`}
              loading={deletingApp === app.id}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const drawerMeta = workshops.find((ws) => ws.code === drawerWorkshop)

  return (
    <div style={{ padding: '20px 24px 32px' }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 22, fontWeight: 600, color: '#1a1a1a', margin: 0, marginBottom: 4 }}>
          飞书配置
        </h2>
        <p style={{ fontSize: 14, color: '#787671', margin: 0 }}>
          设备模块的飞书自建应用凭据与多维表格链接集中存放；巡检数据同步配置按车间管理
        </p>
      </div>

      {loadError && (
        <Alert
          type="error" showIcon style={{ marginBottom: 16 }}
          message="飞书配置加载失败"
          description={loadError}
          action={<Button size="small" onClick={() => setReloadKey((k) => k + 1)}>重试</Button>}
        />
      )}

      <Card
        size="small"
        style={{ marginBottom: 16 }}
        title={<Space size={8}><ApiOutlined />应用凭据（自建应用）</Space>}
        extra={(
          <Button
            size="small"
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => openAppModal(null)}
          >
            新增应用
          </Button>
        )}
      >
        {apps.length === 0 ? (
          <Text type="secondary">
            尚未登记任何自建应用：点「新增应用」登记一次，各车间配置时直接下拉选择，无需重复粘贴凭据
          </Text>
        ) : (
          <Table<FeishuAppSummary>
            rowKey="id"
            size="small"
            columns={appColumns}
            dataSource={apps}
            pagination={false}
            tableLayout="fixed"
            onRow={(app) => (
              { 'data-testid': `feishu-app-${app.app_id}` } as HTMLAttributes<HTMLElement>
            )}
          />
        )}
        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0, marginTop: 8 }}>
          凭据在此登记一次、全车间复用；下方车间清单点「配置 / 编辑」时下拉选择应用。Secret 加密存储、永不回显明文。
        </Paragraph>
      </Card>

      <Card size="small">
        <Spin spinning={loading}>
          <Table<WorkshopRow>
            rowKey="code"
            size="small"
            columns={columns}
            dataSource={rows}
            pagination={false}
            data-testid="feishu-config-table"
          />
        </Spin>
      </Card>

      {drawerMeta && (
        <InspectionFeishuConfigDrawer
          workshopCode={drawerMeta.code}
          workshopLabel={drawerMeta.name}
          open={drawerWorkshop === drawerMeta.code}
          onClose={() => setDrawerWorkshop(null)}
          onSaved={() => setReloadKey((k) => k + 1)}
        />
      )}

      <Modal
        title={editingApp ? '编辑应用' : '新增应用'}
        open={appModalOpen}
        onCancel={() => setAppModalOpen(false)}
        onOk={() => void submitApp()}
        confirmLoading={appSubmitting}
        okText={editingApp ? '保存' : '登记'}
        cancelText="取消"
      >
        <Form form={appForm} layout="vertical" requiredMark={false}>
          <Form.Item
            name="name"
            label="应用名称"
            rules={[{ required: true, message: '请输入应用备注名' }]}
          >
            <Input placeholder="如：设备巡检应用" maxLength={100} />
          </Form.Item>
          <Form.Item
            name="app_id"
            label="App ID"
            rules={[{ required: true, message: '请输入飞书应用 App ID' }]}
            extra={editingApp ? 'App ID 创建后不可修改' : undefined}
          >
            <Input placeholder="cli_xxxxxxxx" disabled={Boolean(editingApp)} autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="app_secret"
            label="App Secret"
            rules={editingApp ? [] : [{ required: true, message: '请输入飞书应用 App Secret' }]}
            extra={editingApp
              ? `已保存（${editingApp.app_secret_masked || '••••••'}），留空保持不变`
              : '加密存储，不回显明文'}
          >
            <Input.Password
              placeholder={editingApp ? '留空保持当前 Secret 不变' : '请输入飞书应用 App Secret'}
              autoComplete="new-password"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
