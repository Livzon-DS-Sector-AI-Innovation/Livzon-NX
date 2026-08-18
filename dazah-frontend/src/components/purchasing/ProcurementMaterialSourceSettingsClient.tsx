'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Input,
  Modal,
  Progress,
  Space,
  Tag,
  Typography,
} from 'antd'
import {
  CheckCircleOutlined,
  LinkOutlined,
  ReloadOutlined,
  SaveOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import {
  saveProcurementMaterialSource,
  syncProcurementMaterialSource,
  testProcurementMaterialSource,
} from '@/actions/purchasing'
import { fetchMaterialSourceConfig } from '@/lib/api/purchasing'
import type {
  MaterialSourceConfigResponse,
  MaterialSourceProbeResponse,
} from '@/types/purchasing'

export const MATERIAL_SYNC_POLL_INTERVAL_MS = 3000
// 必须大于同步单页最长重试窗口（页超时 60s × 3 次重试 + 退避约 3 分钟）
// 和万级记录的正常同步时长（约 100s+），否则正常同步会被误报为超时。
export const MATERIAL_SYNC_HEARTBEAT_TIMEOUT_MS = 300_000

export function formatMaterialSyncProgress(
  fetched: number,
  total: number | null | undefined,
  phase = 'fetching',
  heartbeatAt?: string | null,
  now = Date.now(),
) {
  const heartbeatTime = heartbeatAt ? Date.parse(heartbeatAt) : Number.NaN
  if (
    phase === 'fetching' &&
    Number.isFinite(heartbeatTime) &&
    now - heartbeatTime > MATERIAL_SYNC_HEARTBEAT_TIMEOUT_MS
  ) {
    return '请求可能已超时，可稍后重试'
  }
  if (phase === 'fetching' && fetched === 0) return '正在请求飞书首个页面'
  if (phase === 'persisting') return `正在写入本地数据库，已读取 ${fetched} 条`
  if (phase === 'deactivating') return `正在整理已删除记录，已读取 ${fetched} 条`
  if (total && total > 0) return `已同步 ${fetched} / ${total} 条`
  if (total === 0) return '已读取飞书数据，但有效物料为 0 条'
  if (fetched > 0) return `已拉取 ${fetched} 条`
  return '正在同步物料数据'
}

export function formatMaterialSyncCompletedMessage(count: number) {
  if (count > 0) return `采购物料数据同步完成，本地记录 ${count} 条`
  return '已读取飞书数据，但有效物料为 0 条'
}

type ProcurementMaterialSourceConfig = MaterialSourceConfigResponse & {
  sync_phase?: string
  sync_persisted_count?: number
  sync_heartbeat_at?: string | null
}

type ProcurementMaterialSourceSettingsClientProps = {
  initialConfig: ProcurementMaterialSourceConfig | null
  initialLoadFailed?: boolean
}

function statusTag(status: string | undefined) {
  if (status === 'success') return <Tag color="success">连接正常</Tag>
  if (status === 'error') return <Tag color="error">测试失败</Tag>
  return <Tag>未测试</Tag>
}

export function ProcurementMaterialSourceSettingsClient({
  initialConfig,
  initialLoadFailed = false,
}: ProcurementMaterialSourceSettingsClientProps) {
  const { message } = App.useApp()
  const [sourceUrl, setSourceUrl] = useState(initialConfig?.source_url ?? '')
  const [config, setConfig] = useState<ProcurementMaterialSourceConfig | null>(initialConfig)
  const [probe, setProbe] = useState<MaterialSourceProbeResponse | null>(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const syncing = config?.sync_status === 'syncing'
  const syncFetched = config?.sync_fetched_count ?? 0
  const syncPersisted = config?.sync_persisted_count ?? 0
  const syncTotal = config?.sync_total_records
  const syncPhase = config?.sync_phase ?? 'idle'
  const syncProgressMessage = formatMaterialSyncProgress(
    syncFetched,
    syncTotal,
    syncPhase,
    config?.sync_heartbeat_at,
  )
  const syncPercent =
    syncTotal && syncTotal > 0
      ? Math.min(100, Math.round((syncFetched / syncTotal) * 100))
      : undefined

  const displaySource = probe ?? config
  const latestStatus = probe?.status ?? config?.last_test_status
  const latestError = probe?.error_message ?? config?.last_test_error
  const availableFields = useMemo(() => {
    if (probe?.available_fields?.length) return probe.available_fields
    return config
      ? [
          config.material_code_field,
          config.material_description_field,
          config.rule_model_field,
          config.material_unit_field,
          config.material_template_field,
          config.material_category_field,
          config.material_subcategory_field,
          config.material_cost_category_field,
        ].filter((field): field is string => Boolean(field))
      : []
  }, [config, probe])

  async function handleTest() {
    const nextUrl = sourceUrl.trim()
    if (!nextUrl) {
      message.warning('请输入飞书多维表格链接')
      return
    }
    setTesting(true)
    try {
      const response = await testProcurementMaterialSource({ source_url: nextUrl })
      if (response.code !== 200 || !response.data) {
        message.error(response.message || '物料数据源测试失败')
        return
      }
      setProbe(response.data)
      message.success('飞书多维表格连接测试通过')
    } catch {
      message.error('物料数据源测试失败，请稍后重试')
    } finally {
      setTesting(false)
    }
  }

  async function handleSave() {
    const nextUrl = sourceUrl.trim()
    if (!nextUrl) {
      message.warning('请输入飞书多维表格链接')
      return
    }
    if (config && nextUrl === config.source_url) {
      message.info('该链接已保存，无需重复保存')
      return
    }
    setSaving(true)
    try {
      const response = await saveProcurementMaterialSource({ source_url: nextUrl })
      if (response.code !== 200 || !response.data) {
        message.error(response.message || '物料数据源保存失败')
        return
      }
      setConfig(response.data)
      setProbe(null)
      message.success('采购物料数据源配置已保存')
    } catch {
      message.error('物料数据源保存失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  async function executeSync() {
    try {
      const response = await syncProcurementMaterialSource()
      if (response.code !== 200 || !response.data) {
        message.error(response.message || '采购物料数据同步失败')
        return
      }
      setConfig(response.data.config)
      setProbe(null)
      message.info('采购物料数据同步已启动，正在后台同步，请稍候…')
    } catch {
      message.error('采购物料数据同步启动失败，请稍后重试')
    }
  }

  useEffect(() => {
    if (config?.sync_status !== 'syncing') {
      return
    }
    const timer = setInterval(async () => {
      try {
        const response = await fetchMaterialSourceConfig()
        if (response.code !== 200 || !response.data) {
          return
        }
        const next = response.data
        setConfig(next)
        if (next.sync_status === 'success') {
          message.success(
            formatMaterialSyncCompletedMessage(next.last_sync_record_count ?? 0),
          )
        } else if (next.sync_status === 'error') {
          message.error(next.sync_error || '采购物料数据同步失败')
        }
      } catch {
        // 轮询失败时保持当前状态，等待下一次轮询
      }
    }, MATERIAL_SYNC_POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [config?.sync_status, message])

  function handleSync() {
    if (!config) {
      message.warning('请先保存并测试物料数据源配置')
      return
    }
    Modal.confirm({
      title: '同步物料编码库',
      content: '同步会用飞书多维表格最新数据替换当前本地物料编码库，是否继续？',
      okText: '确认同步',
      cancelText: '取消',
      onOk: executeSync,
    })
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">采购管理 / 系统设置</p>
        <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">采购设置</h1>
        <p className="text-[13px] text-[var(--color-steel)]">
          八类物料明细共用同一张飞书多维表格。平台使用已绑定的企业自建应用访问，采购模块不保存 App Secret。
        </p>
      </div>

      {initialLoadFailed && (
        <Alert
          type="warning"
          showIcon
          message="当前配置读取失败"
          description="可以继续输入链接并测试；保存前会再次校验飞书访问权限和字段。"
        />
      )}

      <Card title="物料数据源" bordered={false}>
        <Space direction="vertical" size="large" className="w-full">
          <div>
            <Typography.Text strong>飞书多维表格链接</Typography.Text>
            <Input
              className="mt-2"
              prefix={<LinkOutlined />}
              value={sourceUrl}
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder="粘贴包含 /base/{app_token} 和 table 参数的链接"
              maxLength={1024}
              allowClear
            />
            <Typography.Text type="secondary" className="mt-1 block text-[12px]">
              保存时自动识别物料编码、物料说明和规格型号字段；旧表中的“规则型号”也可兼容。
            </Typography.Text>
          </div>

          <Space>
            <Button icon={<ReloadOutlined />} loading={testing} onClick={handleTest}>
              测试连接
            </Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
              保存配置
            </Button>
            <Button
              icon={<SyncOutlined />}
              loading={syncing}
              disabled={!config}
              onClick={handleSync}
            >
              同步物料数据
            </Button>
          </Space>

          <Descriptions bordered size="small" column={2} title="解析结果">
            <Descriptions.Item label="App Token">
              {displaySource?.app_token || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="数据表">
              {displaySource?.table_id || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="视图">
              {displaySource?.view_id || '未指定，使用默认视图'}
            </Descriptions.Item>
            <Descriptions.Item label="最近测试">
              {statusTag(latestStatus)}
              {latestError && <span className="ml-2 text-[12px] text-[var(--color-danger)]">{latestError}</span>}
            </Descriptions.Item>
            <Descriptions.Item label="物料编码字段">
              {displaySource?.material_code_field || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="物料说明字段">
              {displaySource?.material_description_field || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="规格型号字段">
              {displaySource?.rule_model_field || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="主要单位字段">
              {displaySource?.material_unit_field || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="物料模板字段">
              {displaySource?.material_template_field || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="物料大类字段">
              {displaySource?.material_category_field || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="物料小类字段">
              {displaySource?.material_subcategory_field || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="物料成本大类字段">
              {displaySource?.material_cost_category_field || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="测试时间">
              {probe?.tested_at || config?.last_tested_at || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="同步状态">
              {config?.sync_status === 'success' && <Tag color="success">同步成功</Tag>}
              {config?.sync_status === 'syncing' && <Tag color="processing">同步中</Tag>}
              {config?.sync_status === 'error' && <Tag color="error">同步失败</Tag>}
              {(!config || !['success', 'syncing', 'error'].includes(config.sync_status)) && (
                <Tag>未同步</Tag>
              )}
              {config?.sync_error && (
                <span className="ml-2 text-[12px] text-[var(--color-danger)]">
                  {config.sync_error}
                </span>
              )}
              {config?.sync_phase && config.sync_phase !== 'idle' && (
                <span className="ml-2 text-[12px] text-[var(--color-steel)]">
                  阶段：{syncPhase === 'fetching' ? '从飞书读取' : syncPhase === 'persisting' ? '写入本地数据库' : syncPhase === 'deactivating' ? '整理已删除记录' : syncPhase === 'completed' ? '已完成' : syncPhase}
                </span>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="最近同步">
              {config?.last_synced_at || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="本地记录数">
              {config?.last_sync_record_count ?? 0}
            </Descriptions.Item>
          </Descriptions>

          {syncing && (
            <div className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-surface-soft)] p-4">
              <div className="flex flex-wrap items-center gap-2">
                <SyncOutlined spin />
                <Typography.Text strong>正在同步物料数据</Typography.Text>
                <Typography.Text type="secondary" className="text-[12px]">
                  {syncProgressMessage}，已落库 {syncPersisted} 条
                </Typography.Text>
              </div>
              {syncTotal && syncTotal > 0 && (
                <Progress percent={syncPercent} status="active" className="mt-2" />
              )}
            </div>
          )}

          {availableFields.length > 0 && (
            <div>
              <Typography.Text type="secondary">已识别字段</Typography.Text>
              <div className="mt-2 flex flex-wrap gap-2">
                {availableFields.map((field) => (
                  <Tag key={field} icon={<CheckCircleOutlined />}>
                    {field}
                  </Tag>
                ))}
              </div>
            </div>
          )}
        </Space>
      </Card>
    </div>
  )
}
