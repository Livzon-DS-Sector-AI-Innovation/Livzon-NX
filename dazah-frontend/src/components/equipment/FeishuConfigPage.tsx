'use client'

// 设备模块飞书配置页：集中存放自建应用凭据状态与各车间多维表格链接。
// 凭据按车间存储（App Secret 加密、永不回显明文），链接为配置时粘贴的
// 完整地址（含租户域名），编辑/测试/同步复用巡检镜像的既有接口。

import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Button, Card, Popover, Space, Spin, Table, Tag, Tooltip, Typography } from 'antd'
import Alert from '@/components/shared/PlatformNotice'
import {
  ApiOutlined, CheckCircleOutlined, CopyOutlined, LinkOutlined,
  SafetyCertificateOutlined, SyncOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
import type { InspectionFeishuConfigDetail } from '@/types/inspection-feishu'
import {
  fetchInspectionFeishuConfigList,
  fetchInspectionFeishuSyncStatus,
  testInspectionFeishuConfig,
  triggerInspectionFeishuSync,
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
  const [syncBriefs, setSyncBriefs] = useState<Record<string, SyncBrief>>({})
  const [syncing, setSyncing] = useState<string | null>(null)
  const [testing, setTesting] = useState<string | null>(null)
  const [drawerWorkshop, setDrawerWorkshop] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const list = await fetchInspectionFeishuConfigList()
      setDetails(list)
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
    return EQUIPMENT_WORKSHOPS.map((ws) => {
      const detail = byCode.get(ws.code) ?? null
      return {
        code: ws.code,
        label: ws.label,
        detail,
        // 环境变量回退的默认车间无凭据/表格时同样视为未配置
        configured: Boolean(detail && detail.app_token && detail.app_id),
      }
    })
  }, [details])

  // 凭据卡片：按 App ID 去重汇总（各车间通常共用一个自建应用）
  const credentialGroups = useMemo(() => {
    const map = new Map<string, InspectionFeishuConfigDetail[]>()
    for (const d of details) {
      if (!d.app_id) continue
      map.set(d.app_id, [...(map.get(d.app_id) ?? []), d])
    }
    return [...map.entries()]
  }, [details])

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

  const drawerMeta = EQUIPMENT_WORKSHOPS.find((ws) => ws.code === drawerWorkshop)

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

      <Card size="small" style={{ marginBottom: 16 }} title={<Space size={8}><ApiOutlined />应用凭据（自建应用）</Space>}>
        {credentialGroups.length === 0 ? (
          <Text type="secondary">尚未配置任何应用凭据，在下方清单选择车间点「配置」开始</Text>
        ) : credentialGroups.map(([appId, group]) => (
          <div key={appId} style={{ display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap', padding: '4px 0' }}>
            <div>
              <div style={{ fontSize: 12, color: '#787671', marginBottom: 2 }}>App ID</div>
              <Space size={4}>
                <Text code>{appId}</Text>
                <Button
                  type="text" size="small" icon={<CopyOutlined />}
                  aria-label="复制 App ID"
                  onClick={() => void copy(appId, 'App ID')}
                />
              </Space>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#787671', marginBottom: 2 }}>App Secret</div>
              <Text type="secondary">
                {group.some((d) => d.app_secret_configured)
                  ? `已配置（${group[0].app_secret_masked || '••••••'}），出于安全不回显明文`
                  : '未配置'}
              </Text>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#787671', marginBottom: 2 }}>使用车间</div>
              <Space size={4} wrap>
                {group.map((d) => <Tag key={d.workshop_code}>{d.workshop_code}</Tag>)}
              </Space>
            </div>
          </div>
        ))}
        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0, marginTop: 8 }}>
          凭据按车间存储、Secret 加密保存；在下方清单对应车间点「编辑」可修改。需要查看 Secret 明文时请前往飞书开放平台。
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
          workshopLabel={drawerMeta.label}
          open={drawerWorkshop === drawerMeta.code}
          onClose={() => setDrawerWorkshop(null)}
          onSaved={() => setReloadKey((k) => k + 1)}
        />
      )}
    </div>
  )
}
