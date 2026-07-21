'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Drawer,
  Input,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import {
  CloudDownloadOutlined,
  ReloadOutlined,
  SaveOutlined,
  SecurityScanOutlined,
} from '@ant-design/icons'
import {
  pullQualityRecordsFromFeishu,
  testQualityFeishuAppSettings,
  testQualityFeishuEntitySetting,
  updateQualityFeishuAppSettings,
  updateQualityFeishuEntitySetting,
} from '@/actions/quality'
import {
  fetchQualityFeishuAppSettings,
  fetchQualityFeishuEntityFieldMappingBundle,
  fetchQualityFeishuEntitySettings,
  fetchQualityFeishuEntityTables,
  formatQualityFeishuTestSummary,
  formatQualitySyncSummary,
} from '@/lib/api/quality'
import type {
  QualityFeishuAppSettingsDetail,
  QualityFeishuEntityFieldMappingBundle,
  QualityFeishuEntitySettingItem,
  QualityFeishuFieldMappingItem,
  QualityFeishuTableOption,
  UpdateQualityFeishuAppSettingsRequest,
  UpdateQualityFeishuEntitySettingRequest,
} from '@/types/quality'
import { ReadOnlyFeishuSourcesPanel } from '@/components/feishu-data/ReadOnlyFeishuSourcesPanel'

type EntityDraftMap = Record<string, UpdateQualityFeishuEntitySettingRequest>
type EntityTableOptionsMap = Record<string, QualityFeishuTableOption[]>
type ResultNotice = {
  type: 'success' | 'error' | 'info' | 'warning'
  title: string
  description?: string
} | null

const EMPTY_APP_FORM: UpdateQualityFeishuAppSettingsRequest = {
  app_id: '',
  app_secret: '',
  is_enabled: true,
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

function createEntityDraft(
  item: QualityFeishuEntitySettingItem
): UpdateQualityFeishuEntitySettingRequest {
  return {
    app_token: item.app_token || '',
    base_table_name: item.base_table_name || '',
    base_table_id: item.base_table_id || '',
    is_enabled: item.is_enabled,
    enable_push_to_feishu: item.enable_push_to_feishu,
    enable_pull_from_feishu: item.enable_pull_from_feishu,
    field_mappings: item.field_mappings || [],
  }
}

function renderStatusTag(value: string | null | undefined) {
  if (value === 'success') return <Tag color="success">正常</Tag>
  if (value === 'failed') return <Tag color="error">失败</Tag>
  return <Tag>未测试</Tag>
}

function getManualMappingFields(
  bundle: QualityFeishuEntityFieldMappingBundle | null
): Array<{ field_key: string; field_label: string; direction: string }> {
  if (!bundle) return []
  const feishuFieldNames = new Set(
    bundle.feishu_fields.map((item) => item.field_name.trim()).filter(Boolean)
  )
  const savedMappings = new Map(
    bundle.field_mappings
      .filter((item) => item.feishu_field?.trim())
      .map((item) => [item.system_field, item.feishu_field!.trim()])
  )
  return bundle.system_fields.filter((field) => {
    const saved = savedMappings.get(field.field_key)
    if (saved) {
      return saved !== field.field_label
    }
    return !feishuFieldNames.has(field.field_label)
  })
}

export function QualityFeishuSettingsPage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [resultNotice, setResultNotice] = useState<ResultNotice>(null)
  const [appForm, setAppForm] = useState<UpdateQualityFeishuAppSettingsRequest>(EMPTY_APP_FORM)
  const [appSettings, setAppSettings] = useState<QualityFeishuAppSettingsDetail | null>(null)
  const [entityItems, setEntityItems] = useState<QualityFeishuEntitySettingItem[]>([])
  const [entityDrafts, setEntityDrafts] = useState<EntityDraftMap>({})
  const [appSaving, setAppSaving] = useState(false)
  const [appTesting, setAppTesting] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [rowSaving, setRowSaving] = useState<Record<string, boolean>>({})
  const [rowTesting, setRowTesting] = useState<Record<string, boolean>>({})
  const [rowLoadingTables, setRowLoadingTables] = useState<Record<string, boolean>>({})
  const [rowTableOptions, setRowTableOptions] = useState<EntityTableOptionsMap>({})
  const [mappingOpen, setMappingOpen] = useState(false)
  const [mappingLoading, setMappingLoading] = useState(false)
  const [mappingSaving, setMappingSaving] = useState(false)
  const [mappingBundle, setMappingBundle] = useState<QualityFeishuEntityFieldMappingBundle | null>(null)
  const [mappingDrafts, setMappingDrafts] = useState<Record<string, string>>({})

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      setLoadError(null)
      const [nextAppSettings, nextEntities] = await Promise.all([
        fetchQualityFeishuAppSettings(),
        fetchQualityFeishuEntitySettings(),
      ])
      setAppSettings(nextAppSettings)
      setAppForm({
        app_id: nextAppSettings.app_id || '',
        app_secret: nextAppSettings.app_secret_masked || '',
        is_enabled: nextAppSettings.is_enabled,
      })
      setEntityItems(nextEntities)
      setRowTableOptions({})
      setEntityDrafts(
        nextEntities.reduce<EntityDraftMap>((acc, item) => {
          acc[item.entity_code] = createEntityDraft(item)
          return acc
        }, {})
      )
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : '加载飞书设置失败')
      setEntityItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const patchEntityDraft = useCallback(
    (entityCode: string, patch: Partial<UpdateQualityFeishuEntitySettingRequest>) => {
      setEntityDrafts((current) => ({
        ...current,
        [entityCode]: {
          ...(current[entityCode] || {
            app_token: '',
            base_table_name: '',
            base_table_id: '',
            is_enabled: false,
            enable_push_to_feishu: false,
            enable_pull_from_feishu: false,
            field_mappings: [],
          }),
          ...patch,
        },
      }))
    },
    []
  )

  const handleSaveApp = useCallback(async () => {
    try {
      setAppSaving(true)
      const appSecret = appForm.app_secret.trim()
      const result = await updateQualityFeishuAppSettings({
        ...appForm,
        app_id: appForm.app_id.trim(),
        app_secret: appSecret === appSettings?.app_secret_masked ? '' : appSecret,
      })
      setAppSettings(result)
      setAppForm((current) => ({
        ...current,
        app_secret: result.app_secret_masked || '',
      }))
      setResultNotice({
        type: 'success',
        title: '飞书应用配置已保存',
      })
      message.success('飞书应用配置已保存')
    } catch (error) {
      const description = error instanceof Error ? error.message : '保存飞书应用配置失败'
      setResultNotice({
        type: 'error',
        title: '保存飞书应用配置失败',
        description,
      })
      message.error(error instanceof Error ? error.message : '保存飞书应用配置失败')
    } finally {
      setAppSaving(false)
    }
  }, [appForm, appSettings, message])

  const handleTestApp = useCallback(async () => {
    try {
      setAppTesting(true)
      const result = await testQualityFeishuAppSettings()
      if (result?.success) {
        setResultNotice({
          type: 'success',
          title: '飞书应用连接测试成功',
          description: formatQualityFeishuTestSummary(result),
        })
        message.success(formatQualityFeishuTestSummary(result))
      } else {
        setResultNotice({
          type: 'warning',
          title: '飞书应用连接测试未通过',
          description: formatQualityFeishuTestSummary(result),
        })
        message.error(formatQualityFeishuTestSummary(result))
      }
      await loadData()
    } catch (error) {
      const description = error instanceof Error ? error.message : '测试飞书应用连接失败'
      setResultNotice({
        type: 'error',
        title: '测试飞书应用连接失败',
        description,
      })
      message.error(error instanceof Error ? error.message : '测试飞书应用连接失败')
    } finally {
      setAppTesting(false)
    }
  }, [loadData, message])

  const handlePull = useCallback(async () => {
    try {
      setPulling(true)
      const result = await pullQualityRecordsFromFeishu()
      if (!result) {
        throw new Error('未收到飞书回拉结果')
      }
      setResultNotice({
        type: result.failed > 0 || result.conflicts > 0 ? 'warning' : 'success',
        title: '飞书回拉已执行',
        description: formatQualitySyncSummary(result),
      })
      message.success(formatQualitySyncSummary(result))
      await loadData()
    } catch (error) {
      const description = error instanceof Error ? error.message : '执行飞书回拉失败'
      setResultNotice({
        type: 'error',
        title: '执行飞书回拉失败',
        description,
      })
      message.error(error instanceof Error ? error.message : '执行飞书回拉失败')
    } finally {
      setPulling(false)
    }
  }, [loadData, message])

  const handleSaveEntity = useCallback(
    async (entityCode: string) => {
      try {
        setRowSaving((current) => ({ ...current, [entityCode]: true }))
        const draft = entityDrafts[entityCode]
        if (!draft) return
        const result = await updateQualityFeishuEntitySetting(entityCode, {
          ...draft,
          base_table_name: draft.base_table_name?.trim() || '',
          base_table_id: draft.base_table_id?.trim() || '',
        })
        if (!result) return
        await loadData()
        setResultNotice({
          type: 'success',
          title: `${result.entity_name} 配置已保存`,
        })
        message.success(`${result.entity_name} 配置已保存`)
      } catch (error) {
        const description = error instanceof Error ? error.message : '保存实体配置失败'
        setResultNotice({
          type: 'error',
          title: '保存实体配置失败',
          description,
        })
        message.error(error instanceof Error ? error.message : '保存实体配置失败')
      } finally {
        setRowSaving((current) => ({ ...current, [entityCode]: false }))
      }
    },
    [entityDrafts, loadData, message]
  )

  const handleTestEntity = useCallback(
    async (entityCode: string, entityName: string) => {
      try {
        setRowTesting((current) => ({ ...current, [entityCode]: true }))
        const result = await testQualityFeishuEntitySetting(entityCode)
        if (result?.success) {
          setResultNotice({
            type: 'success',
            title: `${entityName} 连接测试成功`,
            description: formatQualityFeishuTestSummary(result),
          })
          message.success(formatQualityFeishuTestSummary(result))
        } else {
          setResultNotice({
            type: 'warning',
            title: `${entityName} 连接测试未通过`,
            description: formatQualityFeishuTestSummary(result),
          })
          message.error(formatQualityFeishuTestSummary(result))
        }
        await loadData()
      } catch (error) {
        const description =
          error instanceof Error ? error.message : `${entityName} 连接测试失败`
        setResultNotice({
          type: 'error',
          title: `${entityName} 连接测试失败`,
          description,
        })
        message.error(
          error instanceof Error ? error.message : `${entityName} 连接测试失败`
        )
      } finally {
        setRowTesting((current) => ({ ...current, [entityCode]: false }))
      }
    },
    [loadData, message]
  )

  const openFieldMapping = useCallback(
    async (record: QualityFeishuEntitySettingItem) => {
      try {
        setMappingLoading(true)
        setMappingOpen(true)
        const bundle = await fetchQualityFeishuEntityFieldMappingBundle(record.entity_code, {
          app_token: entityDrafts[record.entity_code]?.app_token || '',
          table_id: entityDrafts[record.entity_code]?.base_table_id || '',
        })
        setMappingBundle(bundle)
        setMappingDrafts(
          bundle.field_mappings.reduce<Record<string, string>>((acc, item) => {
            acc[item.system_field] = item.feishu_field || ''
            return acc
          }, {})
        )
      } catch (error) {
        setMappingOpen(false)
        setResultNotice({
          type: 'error',
          title: '读取字段对齐配置失败',
          description: error instanceof Error ? error.message : '读取字段对齐配置失败',
        })
        message.error(error instanceof Error ? error.message : '读取字段对齐配置失败')
      } finally {
        setMappingLoading(false)
      }
    },
    [entityDrafts, message]
  )

  const saveFieldMapping = useCallback(async () => {
    if (!mappingBundle) return
    try {
      setMappingSaving(true)
      const currentDraft = entityDrafts[mappingBundle.entity_code]
      if (!currentDraft) return
      const fieldMappings: QualityFeishuFieldMappingItem[] = getManualMappingFields(mappingBundle)
        .map((item) => ({
          system_field: item.field_key,
          feishu_field: mappingDrafts[item.field_key] || null,
        }))
        .filter((item) => item.feishu_field)
      const result = await updateQualityFeishuEntitySetting(mappingBundle.entity_code, {
        ...currentDraft,
        field_mappings: fieldMappings,
      })
      if (!result) return
      await loadData()
      setResultNotice({
        type: 'success',
        title: `${mappingBundle.entity_name} 字段对齐已保存`,
      })
      setMappingOpen(false)
      message.success(`${mappingBundle.entity_name} 字段对齐已保存`)
    } catch (error) {
      setResultNotice({
        type: 'error',
        title: '保存字段对齐配置失败',
        description: error instanceof Error ? error.message : '保存字段对齐配置失败',
      })
      message.error(error instanceof Error ? error.message : '保存字段对齐配置失败')
    } finally {
      setMappingSaving(false)
    }
  }, [entityDrafts, loadData, mappingBundle, mappingDrafts, message])

  const manualMappingFields = useMemo(
    () => getManualMappingFields(mappingBundle),
    [mappingBundle]
  )

  const handleLoadTables = useCallback(
    async (entityCode: string) => {
      try {
        setRowLoadingTables((current) => ({ ...current, [entityCode]: true }))
        const tables = await fetchQualityFeishuEntityTables(
          entityCode,
          entityDrafts[entityCode]?.app_token || '',
          entityDrafts[entityCode]?.base_table_id || ''
        )
        if (tables.length === 1) {
          patchEntityDraft(entityCode, {
            base_table_name: tables[0].table_name,
            base_table_id: tables[0].table_id,
          })
        }
        setRowTableOptions((current) => ({ ...current, [entityCode]: tables }))
        setResultNotice({
          type: 'success',
          title: '飞书表列表读取成功',
          description: `已读取 ${tables.length} 张表`,
        })
        message.success(`已读取 ${tables.length} 张表`)
      } catch (error) {
        setResultNotice({
          type: 'error',
          title: '读取飞书表列表失败',
          description: error instanceof Error ? error.message : '读取飞书表列表失败',
        })
        message.error(error instanceof Error ? error.message : '读取飞书表列表失败')
      } finally {
        setRowLoadingTables((current) => ({ ...current, [entityCode]: false }))
      }
    },
    [entityDrafts, message, patchEntityDraft]
  )

  const columns = useMemo(
    () => [
      {
        title: '分组',
        dataIndex: 'entity_group',
        key: 'entity_group',
        width: 140,
        render: (value: string) => <Tag color="blue">{value}</Tag>,
      },
      {
        title: '实体',
        dataIndex: 'entity_name',
        key: 'entity_name',
        width: 220,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Space orientation="vertical" size={2}>
            <Typography.Text>{record.entity_name}</Typography.Text>
            {record.source_note ? (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {record.source_note}
              </Typography.Text>
            ) : null}
          </Space>
        ),
      },
      {
        title: 'App Token',
        key: 'app_token',
        width: 220,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Input
            value={entityDrafts[record.entity_code]?.app_token || ''}
            placeholder="例如：bascnxxxxxxxx"
            onChange={(event) =>
              patchEntityDraft(record.entity_code, { app_token: event.target.value })
            }
          />
        ),
      },
      {
        title: 'Base 表名称',
        key: 'base_table_name',
        width: 260,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Select
            showSearch
            allowClear
            placeholder="可读取后直接选择"
            value={entityDrafts[record.entity_code]?.base_table_name || undefined}
            options={(rowTableOptions[record.entity_code] || []).map((item) => ({
              label: item.table_name,
              value: item.table_name,
            }))}
            onChange={(value) => {
              const option = (rowTableOptions[record.entity_code] || []).find(
                (item) => item.table_name === value
              )
              patchEntityDraft(record.entity_code, {
                base_table_name: value || '',
                base_table_id: option?.table_id || entityDrafts[record.entity_code]?.base_table_id || '',
              })
            }}
            onClear={() =>
              patchEntityDraft(record.entity_code, {
                base_table_name: '',
              })
            }
          />
        ),
      },
      {
        title: 'Base Table ID',
        key: 'base_table_id',
        width: 220,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Input
            value={entityDrafts[record.entity_code]?.base_table_id || ''}
            placeholder="例如：tblxxxxxxxx"
            onChange={(event) =>
              patchEntityDraft(record.entity_code, { base_table_id: event.target.value })
            }
          />
        ),
      },
      {
        title: '启用',
        key: 'is_enabled',
        width: 90,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Switch
            checked={entityDrafts[record.entity_code]?.is_enabled || false}
            onChange={(checked) => patchEntityDraft(record.entity_code, { is_enabled: checked })}
          />
        ),
      },
      {
        title: '推送',
        key: 'enable_push_to_feishu',
        width: 90,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Switch
            checked={entityDrafts[record.entity_code]?.enable_push_to_feishu || false}
            onChange={(checked) =>
              patchEntityDraft(record.entity_code, { enable_push_to_feishu: checked })
            }
          />
        ),
      },
      {
        title: '回拉',
        key: 'enable_pull_from_feishu',
        width: 90,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Switch
            checked={entityDrafts[record.entity_code]?.enable_pull_from_feishu || false}
            onChange={(checked) =>
              patchEntityDraft(record.entity_code, { enable_pull_from_feishu: checked })
            }
          />
        ),
      },
      {
        title: '最近状态',
        key: 'last_status',
        width: 220,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Space orientation="vertical" size={2}>
            {renderStatusTag(record.last_sync_status)}
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              最近测试：{formatDateTime(record.last_synced_at)}
            </Typography.Text>
          </Space>
        ),
      },
      {
        title: '操作',
        key: 'actions',
        width: 260,
        fixed: 'right' as const,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Space>
            <Button
              size="small"
              loading={rowLoadingTables[record.entity_code]}
              onClick={() => void handleLoadTables(record.entity_code)}
            >
              读取表
            </Button>
            <Button
              size="small"
              onClick={() => void openFieldMapping(record)}
            >
              字段对齐
            </Button>
            <Button
              size="small"
              type="primary"
              icon={<SaveOutlined />}
              loading={rowSaving[record.entity_code]}
              onClick={() => void handleSaveEntity(record.entity_code)}
            >
              保存
            </Button>
            <Button
              size="small"
              icon={<SecurityScanOutlined />}
              loading={rowTesting[record.entity_code]}
              onClick={() => void handleTestEntity(record.entity_code, record.entity_name)}
            >
              测试
            </Button>
          </Space>
        ),
      },
    ],
    [
      entityDrafts,
      handleLoadTables,
      handleSaveEntity,
      handleTestEntity,
      patchEntityDraft,
      rowLoadingTables,
      rowSaving,
      rowTableOptions,
      rowTesting,
    ]
  )

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 8 }}>
          飞书设置
        </Typography.Title>
        <Typography.Text type="secondary">
          在这里维护质量模块的飞书应用信息、各台账对应的 Base 表，以及手动执行回拉验证。
        </Typography.Text>
      </div>

      {loadError ? (
        <Alert
          type="error"
          showIcon
          title="飞书设置加载失败"
          description={loadError}
        />
      ) : null}
      {resultNotice ? (
        <Alert
          type={resultNotice.type}
          showIcon
          closable
          onClose={() => setResultNotice(null)}
          title={resultNotice.title}
          description={resultNotice.description}
        />
      ) : null}

      <Card
        title="飞书应用信息"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => void loadData()} loading={loading}>
              刷新
            </Button>
            <Button
              icon={<SecurityScanOutlined />}
              onClick={() => void handleTestApp()}
              loading={appTesting}
            >
              测试连接
            </Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={() => void handleSaveApp()}
              loading={appSaving}
            >
              保存配置
            </Button>
          </Space>
        }
      >
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 120 }}>
              App ID
            </Button>
            <Input
              value={appForm.app_id}
              placeholder="请输入飞书应用 App ID"
              onChange={(event) =>
                setAppForm((current) => ({ ...current, app_id: event.target.value }))
              }
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 120 }}>
              App Secret
            </Button>
            <Input.Password
              value={appForm.app_secret}
              placeholder="请输入飞书应用 App Secret"
              onChange={(event) =>
                setAppForm((current) => ({ ...current, app_secret: event.target.value }))
              }
            />
          </Space.Compact>
          <Space size={12}>
            <Typography.Text>启用飞书同步</Typography.Text>
            <Switch
              checked={appForm.is_enabled}
              onChange={(checked) =>
                setAppForm((current) => ({ ...current, is_enabled: checked }))
              }
            />
            {renderStatusTag(appSettings?.last_test_status)}
            <Typography.Text type="secondary">
              最近测试：{formatDateTime(appSettings?.last_tested_at)}
            </Typography.Text>
          </Space>
          {appSettings?.last_test_error ? (
            <Alert type="warning" showIcon title={appSettings.last_test_error} />
          ) : null}
        </Space>
      </Card>

      <Card
        title="质量实体同步配置"
        extra={
          <Button
            type="primary"
            icon={<CloudDownloadOutlined />}
            onClick={() => void handlePull()}
            loading={pulling}
          >
            手动回拉已启用数据
          </Button>
        }
      >
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Table<QualityFeishuEntitySettingItem>
            rowKey="entity_code"
            loading={loading}
            columns={columns}
            dataSource={entityItems}
            pagination={false}
            scroll={{ x: 1860 }}
          />
        </Space>
      </Card>

      <ReadOnlyFeishuSourcesPanel
        moduleCode="quality"
        pageOptions={[
          { label: '飞书数据展示', value: 'quality.data' },
        ]}
      />

      <Drawer
        title={mappingBundle ? `${mappingBundle.entity_name} 字段对齐` : '字段对齐'}
        open={mappingOpen}
        size="large"
        onClose={() => setMappingOpen(false)}
        extra={
          <Space>
            <Button onClick={() => setMappingOpen(false)}>关闭</Button>
            <Button type="primary" loading={mappingSaving} onClick={() => void saveFieldMapping()}>
              保存字段对齐
            </Button>
          </Space>
        }
      >
        {mappingLoading ? (
          <Typography.Text type="secondary">正在读取字段信息...</Typography.Text>
        ) : mappingBundle ? (
          <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
            <Alert
              type="info"
              showIcon
              title="这里只维护需要人工指定的字段别名"
              description="飞书字段名与系统字段名完全一致的部分，系统会按各模块代码里的默认字段直接同步；这里只展示名称不一致、需要你手工指定映射的字段。"
            />
            {manualMappingFields.length ? (
              <Table
                rowKey="field_key"
                pagination={false}
                dataSource={manualMappingFields}
                columns={[
                  {
                    title: '系统字段',
                    dataIndex: 'field_label',
                    key: 'field_label',
                    width: 220,
                  },
                  {
                    title: '方向',
                    dataIndex: 'direction',
                    key: 'direction',
                    width: 100,
                    render: (value: string) => {
                      if (value === 'push') return <Tag color="blue">推送</Tag>
                      if (value === 'pull') return <Tag color="green">回拉</Tag>
                      return <Tag color="purple">双向</Tag>
                    },
                  },
                  {
                    title: '飞书字段',
                    key: 'feishu_field',
                    render: (_: unknown, record: { field_key: string }) => (
                      <Select
                        showSearch
                        allowClear
                        placeholder="请选择飞书字段"
                        value={mappingDrafts[record.field_key] || undefined}
                        options={mappingBundle.feishu_fields.map((item) => ({
                          label: item.field_name,
                          value: item.field_name,
                        }))}
                        onChange={(value) =>
                          setMappingDrafts((current) => ({
                            ...current,
                            [record.field_key]: value || '',
                          }))
                        }
                      />
                    ),
                  },
                ]}
              />
            ) : (
              <Alert
                type="success"
                showIcon
                title="当前实体没有需要手工配置的字段别名"
                description="同名字段会按模块里现有代码直接同步，不需要再额外维护字段映射。"
              />
            )}
          </Space>
        ) : (
          <Alert type="warning" showIcon title="未读取到字段对齐信息" />
        )}
      </Drawer>
    </Space>
  )
}
