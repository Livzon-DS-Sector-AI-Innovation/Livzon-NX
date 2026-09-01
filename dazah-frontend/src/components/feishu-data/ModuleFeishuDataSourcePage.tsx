'use client'

import {
  ApiOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
} from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  feishuDataSourceApi,
  getFeishuModuleDefinition,
  type FeishuConfig,
  type FeishuConfigInput,
  type FeishuModuleCode,
  type FeishuPageBinding,
  type FeishuResource,
  type FeishuSourceRoot,
} from '@/lib/feishu-data-source'

import { FeishuConfigPageHeader } from './FeishuConfigPageHeader'

type Props = { moduleCode: FeishuModuleCode }
type RootInput = { name: string; source_type: 'wiki' | 'base'; source_url: string }

export type FeishuWriteActions = {
  saveConfig: (values: FeishuConfigInput) => Promise<FeishuConfig>
  testConfig: (values: FeishuConfigInput) => Promise<{
    ok: boolean
    steps: Array<{ name: string; status: string; message: string }>
  }>
  createRoot: (values: RootInput) => Promise<unknown>
  deleteRoot: (rootId: string) => Promise<unknown>
  discoverRoot: (rootId: string) => Promise<unknown>
  syncResource: (resourceId: string) => Promise<unknown>
  syncResources: (resourceIds: string[]) => Promise<unknown>
  saveBindings: (pageKey: string, bindings: FeishuPageBinding[]) => Promise<unknown>
}

type PropsWithActions = Props & {
  writeActions?: FeishuWriteActions
  /** 是否展示「Wiki / 多维表格入口」与「资源目录」区块（默认展示） */
  showRootsAndCatalog?: boolean
}

const EMPTY_CONFIG: FeishuConfigInput = {
  config_name: '飞书数据源',
  app_id: '',
  app_secret: '',
  is_active: true,
  timezone: 'Asia/Shanghai',
  daily_sync_time: '02:00',
  remark: '',
}

function statusTag(status?: string) {
  if (status === 'success') return <Tag color="success">成功</Tag>
  if (status === 'running' || status === 'discovering') return <Tag color="processing">执行中</Tag>
  if (status === 'failed') return <Tag color="error">失败</Tag>
  return <Tag>待执行</Tag>
}

function sourcePathLabel(path: FeishuResource['source_path']) {
  return path.map((item) => item.title).filter(Boolean).join(' / ') || '-'
}

export function ModuleFeishuDataSourcePage({
  moduleCode,
  writeActions,
  showRootsAndCatalog = true,
}: PropsWithActions) {
  const { message } = App.useApp()
  const definition = useMemo(() => getFeishuModuleDefinition(moduleCode), [moduleCode])
  const [configForm] = Form.useForm<FeishuConfigInput>()
  const [rootForm] = Form.useForm<RootInput>()
  const [config, setConfig] = useState<FeishuConfig | null>(null)
  const [roots, setRoots] = useState<FeishuSourceRoot[]>([])
  const [resources, setResources] = useState<FeishuResource[]>([])
  const [pageKey, setPageKey] = useState(definition.pages[0]?.value || '')
  const [bindings, setBindings] = useState<FeishuPageBinding[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [rootModalOpen, setRootModalOpen] = useState(false)
  const [selectedResourceIds, setSelectedResourceIds] = useState<string[]>([])
  const supportsResourceDelete = moduleCode === 'energy'
  const sourcePathFilters = useMemo(
    () => Array.from(new Set(resources.map((item) => sourcePathLabel(item.source_path))))
      .sort((left, right) => left.localeCompare(right, 'zh-CN'))
      .map((path) => ({ text: path, value: path })),
    [resources],
  )

  const loadCatalog = useCallback(async (currentConfig?: FeishuConfig | null) => {
    // 「页面数据表映射」卡依赖 resources：即使隐藏 Wiki 入口/资源目录区块
    // （如仓储合并设置页），也必须拉取资源目录，否则映射卡永远为空。
    // 隐藏模式下仅跳过 roots（入口发现）拉取。
    const resourcesPromise = feishuDataSourceApi.listResources(moduleCode)
    if (!showRootsAndCatalog) {
      const nextResources = await resourcesPromise
      setRoots([])
      setResources(nextResources)
      return
    }
    const [nextRoots, nextResources] = await Promise.all([
      feishuDataSourceApi.listRoots(moduleCode, currentConfig?.id),
      resourcesPromise,
    ])
    setRoots(nextRoots)
    setResources(nextResources)
  }, [moduleCode, showRootsAndCatalog])

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const nextConfig = await feishuDataSourceApi.getConfig(moduleCode)
      setConfig(nextConfig)
      configForm.setFieldsValue({
        ...EMPTY_CONFIG,
        id: nextConfig.id,
        config_name: nextConfig.config_name,
        app_id: nextConfig.app_id,
        app_secret: '',
        is_active: nextConfig.is_active,
        timezone: nextConfig.timezone || EMPTY_CONFIG.timezone,
        daily_sync_time: nextConfig.daily_sync_time || EMPTY_CONFIG.daily_sync_time,
        remark: nextConfig.remark,
      })
      if (nextConfig.app_secret_configured) {
        // 目录拉取失败只提示，不覆盖已回填的凭证表单
        await loadCatalog(nextConfig).catch((catalogError) => {
          message.error(
            catalogError instanceof Error
              ? catalogError.message
              : '加载飞书目录失败',
          )
        })
      } else {
        setRoots([])
        setResources([])
      }
    } catch (error) {
      configForm.setFieldsValue(EMPTY_CONFIG)
      message.error(error instanceof Error ? error.message : '加载飞书配置失败')
    } finally {
      setLoading(false)
    }
  }, [configForm, loadCatalog, message, moduleCode])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadAll(), 0)
    return () => window.clearTimeout(timer)
  }, [loadAll])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (!pageKey || !config?.app_secret_configured) {
        setBindings([])
        return
      }
      void feishuDataSourceApi.getBindings(moduleCode, pageKey)
        .then(setBindings)
        .catch(() => setBindings([]))
    }, 0)
    return () => window.clearTimeout(timer)
  }, [config?.app_secret_configured, moduleCode, pageKey])

  const saveConfig = async () => {
    try {
      const values = await configForm.validateFields()
      setSaving(true)
      const saved = writeActions
        ? await writeActions.saveConfig({ ...values, id: config?.id })
        : await feishuDataSourceApi.saveConfig(moduleCode, { ...values, id: config?.id })
      setConfig(saved)
      configForm.setFieldValue('app_secret', '')
      await loadCatalog(saved)
      message.success('应用凭据已保存')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const testConfig = async () => {
    try {
      const values = await configForm.validateFields()
      setTesting(true)
      const result = writeActions
        ? await writeActions.testConfig({ ...values, id: config?.id })
        : await feishuDataSourceApi.testConfig(moduleCode, { ...values, id: config?.id })
      const failed = result.steps?.filter((item) => item.status === 'error') || []
      if (result.ok === false || failed.length) message.error(failed.map((item) => item.message).join('；') || '连接测试失败')
      else message.success('App ID / Secret 连通性正常')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '连接测试失败')
    } finally {
      setTesting(false)
    }
  }

  const addRoot = async () => {
    try {
      const values = await rootForm.validateFields()
      setBusyKey('new-root')
      if (writeActions) await writeActions.createRoot(values)
      else await feishuDataSourceApi.createRoot(moduleCode, values, config?.id)
      rootForm.resetFields()
      setRootModalOpen(false)
      await loadCatalog(config)
      message.success('数据入口已添加')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '添加入口失败')
    } finally {
      setBusyKey(null)
    }
  }

  const runRootAction = async (root: FeishuSourceRoot, action: 'discover' | 'delete') => {
    try {
      setBusyKey(`${action}:${root.id}`)
      if (action === 'discover') {
        if (writeActions) await writeActions.discoverRoot(root.id)
        else await feishuDataSourceApi.discoverRoot(moduleCode, root.id)
      } else if (writeActions) await writeActions.deleteRoot(root.id)
      else await feishuDataSourceApi.deleteRoot(moduleCode, root.id)
      await loadCatalog(config)
      message.success(action === 'discover' ? '资源发现完成' : '入口已停用')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败')
    } finally {
      setBusyKey(null)
    }
  }

  const syncResource = async (resource: FeishuResource) => {
    try {
      setBusyKey(`sync:${resource.id}`)
      if (writeActions) await writeActions.syncResource(resource.id)
      else await feishuDataSourceApi.syncResource(moduleCode, resource.id)
      await loadCatalog(config)
      message.success('完整镜像同步成功')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '同步失败')
    } finally {
      setBusyKey(null)
    }
  }

  const syncSelectedResources = async () => {
    if (!selectedResourceIds.length) return
    try {
      setBusyKey('batch-sync')
      if (writeActions) await writeActions.syncResources(selectedResourceIds)
      else await feishuDataSourceApi.syncResources(moduleCode, selectedResourceIds)
      await loadCatalog(config)
      message.success(`已完成 ${selectedResourceIds.length} 个资源的批量同步`)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '批量同步失败')
    } finally {
      setBusyKey(null)
    }
  }

  const deleteResources = async (resourceIds: string[]) => {
    try {
      setBusyKey('batch-delete')
      const result = await feishuDataSourceApi.deleteResources(moduleCode, resourceIds)
      setSelectedResourceIds((current) => current.filter((id) => !resourceIds.includes(id)))
      setBindings((current) => current.filter((item) => !resourceIds.includes(item.resource_id)))
      await loadCatalog(config)
      message.success(
        `已删除 ${result.deleted_count} 个资源、${result.snapshot_count} 个快照和 ${result.snapshot_row_count} 行快照数据`,
      )
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除资源失败')
      throw error
    } finally {
      setBusyKey(null)
    }
  }

  const confirmDeleteResources = (resourceIds: string[]) => {
    const targets = resources.filter((item) => resourceIds.includes(item.id))
    Modal.confirm({
      title: `确认删除 ${targets.length} 个资源？`,
      content: `将永久删除“${targets.map((item) => item.title).join('、')}”及其页面映射、字段映射、指标事实、全部快照和数据库记录。此操作不会删除飞书原表，但不可撤销。`,
      okText: '永久删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteResources(resourceIds),
    })
  }

  const selectedIds = bindings.map((item) => item.resource_id)
  const saveBindings = async () => {
    if (!pageKey) return
    try {
      setBusyKey('bindings')
      if (writeActions) await writeActions.saveBindings(pageKey, bindings)
      else await feishuDataSourceApi.saveBindings(moduleCode, pageKey, bindings)
      message.success('页面映射已发布')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '发布映射失败')
    } finally {
      setBusyKey(null)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[420px] items-center justify-center">
        <Spin size="large" />
        {/* useForm 实例必须在 Form 元素上连接：loading 期间先挂载隐藏表单，避免控制台警告 */}
        <div className="hidden">
          <Form form={configForm} />
          <Form form={rootForm} />
        </div>
      </div>
    )
  }

  return (
    <main className="mx-auto max-w-[1440px] px-6 py-7">
      <FeishuConfigPageHeader moduleLabel={definition.moduleLabel} />
      <Space orientation="vertical" size={16} className="w-full">
        <Card
          title={<Space><ApiOutlined />应用凭据</Space>}
          extra={<Space wrap>
            <Button icon={<ExperimentOutlined />} loading={testing} onClick={() => void testConfig()}>测试连接</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => void saveConfig()}>保存凭据</Button>
          </Space>}
        >
          <Form form={configForm} layout="vertical" initialValues={EMPTY_CONFIG}>
            <div className="grid grid-cols-1 gap-x-5 md:grid-cols-2 lg:grid-cols-3">
              <Form.Item name="config_name" label="配置名称" rules={[{ required: true, message: '请输入配置名称' }]}><Input /></Form.Item>
              <Form.Item name="app_id" label="App ID" rules={[{ required: true, message: '请输入 App ID' }]}><Input autoComplete="off" /></Form.Item>
              <Form.Item name="app_secret" label="App Secret" extra={config?.app_secret_configured ? '留空保留已加密密钥' : '首次保存必填'}><Input.Password autoComplete="new-password" /></Form.Item>
              <Form.Item name="daily_sync_time" label="每日同步时间" rules={[{ required: true }]}><Input type="time" /></Form.Item>
              <Form.Item name="timezone" label="时区" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="is_active" label="启用自动同步" valuePropName="checked"><Switch /></Form.Item>
            </div>
            <Form.Item name="remark" label="备注"><Input.TextArea rows={2} /></Form.Item>
          </Form>
        </Card>

        {showRootsAndCatalog && (
        <>
        <Card title="Wiki / 多维表格入口" extra={<Button type="primary" icon={<PlusOutlined />} disabled={!config?.app_secret_configured} onClick={() => setRootModalOpen(true)}>添加入口</Button>}>
          {!config?.app_secret_configured ? <Alert showIcon type="info" title="请先保存应用凭据，再添加一个或多个 Wiki/Base 入口。" /> : (
            <Table<FeishuSourceRoot>
              rowKey="id"
              dataSource={roots}
              pagination={false}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未添加数据入口" /> }}
              columns={[
                { title: '入口名称', dataIndex: 'name' },
                { title: '类型', dataIndex: 'source_type', width: 100, render: (value) => <Tag>{String(value).toUpperCase()}</Tag> },
                { title: '发现状态', dataIndex: 'discovery_status', width: 120, render: statusTag },
                { title: '最近发现', dataIndex: 'last_discovered_at', width: 190, render: (value) => value ? new Date(value).toLocaleString('zh-CN') : '-' },
                { title: '错误', dataIndex: 'discovery_error', ellipsis: true, render: (value) => value || '-' },
                { title: '操作', width: 200, render: (_, root) => <Space>
                  <Button size="small" icon={<ReloadOutlined />} loading={busyKey === `discover:${root.id}`} onClick={() => void runRootAction(root, 'discover')}>发现</Button>
                  <Popconfirm title="停用该入口？已发布的完整镜像不会立即删除。" onConfirm={() => void runRootAction(root, 'delete')}><Button danger size="small" icon={<DeleteOutlined />} loading={busyKey === `delete:${root.id}`} /></Popconfirm>
                </Space> },
              ]}
            />
          )}
        </Card>

        <Card
          title="资源目录"
          extra={<Space wrap>
            <Button
              icon={<SyncOutlined />}
              disabled={!selectedResourceIds.length || Boolean(busyKey)}
              loading={busyKey === 'batch-sync'}
              onClick={() => void syncSelectedResources()}
            >
              批量同步{selectedResourceIds.length ? `（${selectedResourceIds.length}）` : ''}
            </Button>
            {supportsResourceDelete && (
              <Button
                danger
                icon={<DeleteOutlined />}
                disabled={!selectedResourceIds.length || Boolean(busyKey)}
                loading={busyKey === 'batch-delete'}
                onClick={() => confirmDeleteResources(selectedResourceIds)}
              >
                批量删除{selectedResourceIds.length ? `（${selectedResourceIds.length}）` : ''}
              </Button>
            )}
            <Button icon={<ReloadOutlined />} disabled={!config?.app_secret_configured || Boolean(busyKey)} onClick={() => void loadCatalog(config)}>刷新本地目录</Button>
          </Space>}
        >
          {selectedResourceIds.length > 0 && (
            <Alert
              className="mb-3"
              type="info"
              showIcon
              title={`已选择 ${selectedResourceIds.length} 个资源，可执行批量同步${supportsResourceDelete ? '或批量删除' : ''}。`}
            />
          )}
          <Table<FeishuResource>
            rowKey="id"
            dataSource={resources}
            pagination={{ pageSize: 10, showSizeChanger: false }}
            scroll={{ x: 900 }}
            rowSelection={{
              preserveSelectedRowKeys: true,
              selectedRowKeys: selectedResourceIds,
              onChange: (keys) => setSelectedResourceIds(keys.map(String)),
            }}
            columns={[
              { title: '数据表', dataIndex: 'title' },
              {
                title: '来源路径',
                dataIndex: 'source_path',
                filters: sourcePathFilters,
                filterSearch: true,
                onFilter: (value, item) => sourcePathLabel(item.source_path) === String(value),
                render: sourcePathLabel,
              },
              { title: 'Table ID', dataIndex: 'table_id', width: 190 },
              { title: '字段/记录', width: 110, render: (_, item) => `${item.field_count}/${item.record_count}` },
              { title: '同步状态', dataIndex: 'sync_status', width: 110, render: statusTag },
              { title: '最近完整同步', dataIndex: 'last_complete_sync_at', width: 190, render: (value) => value ? new Date(value).toLocaleString('zh-CN') : '-' },
              { title: '操作', width: supportsResourceDelete ? 170 : 100, fixed: 'right', render: (_, item) => <Space>
                <Button size="small" icon={<SyncOutlined />} disabled={Boolean(busyKey)} loading={busyKey === `sync:${item.id}`} onClick={() => void syncResource(item)}>同步</Button>
                {supportsResourceDelete && (
                  <Button danger size="small" icon={<DeleteOutlined />} disabled={Boolean(busyKey)} onClick={() => confirmDeleteResources([item.id])}>删除</Button>
                )}
              </Space> },
            ]}
          />
        </Card>

        </>
        )}
        <Card title="页面数据表映射" extra={<Button type="primary" loading={busyKey === 'bindings'} disabled={!pageKey} onClick={() => void saveBindings()}>发布映射</Button>}>
          <Alert className="mb-4" type="info" showIcon title="选择菜单页面并点击勾选一张或多张数据表；数据展示页会按选择顺序生成页签。" />
          <Space orientation="vertical" size={12} className="w-full">
            <Select
              showSearch
              optionFilterProp="label"
              value={pageKey || undefined}
              options={definition.pages}
              placeholder="搜索并选择任意层级菜单页面"
              className="w-full max-w-[520px]"
              onChange={setPageKey}
            />
            <Table<FeishuResource>
              rowKey="id"
              dataSource={resources}
              pagination={{ pageSize: 8 }}
              rowSelection={{
                preserveSelectedRowKeys: true,
                selectedRowKeys: selectedIds,
                onChange: (keys) => {
                  const ids = keys.map(String)
                  setBindings(ids.map((id, index) => {
                    const existing = bindings.find((item) => item.resource_id === id)
                    const resource = resources.find((item) => item.id === id)
                    return existing ? { ...existing, sort_order: index, is_default: index === 0 } : {
                      resource_id: id,
                      tab_name: resource?.title || `数据表 ${index + 1}`,
                      sort_order: index,
                      is_default: index === 0,
                      is_enabled: true,
                      visible_field_ids: [],
                    }
                  }))
                },
              }}
              columns={[
                { title: '数据表', dataIndex: 'title' },
                { title: '页签名称', width: 240, render: (_, item) => <Input size="small" disabled={!selectedIds.includes(item.id)} value={bindings.find((binding) => binding.resource_id === item.id)?.tab_name || item.title} onChange={(event) => setBindings((current) => current.map((binding) => binding.resource_id === item.id ? { ...binding, tab_name: event.target.value } : binding))} /> },
                {
                  title: '来源路径',
                  dataIndex: 'source_path',
                  filters: sourcePathFilters,
                  filterSearch: true,
                  onFilter: (value, item) => sourcePathLabel(item.source_path) === String(value),
                  render: sourcePathLabel,
                },
                { title: '同步状态', dataIndex: 'sync_status', width: 110, render: statusTag },
              ]}
            />
          </Space>
        </Card>
      </Space>

      <Modal title="添加飞书数据入口" open={rootModalOpen} forceRender confirmLoading={busyKey === 'new-root'} onOk={() => void addRoot()} onCancel={() => setRootModalOpen(false)} destroyOnHidden>
        <Form form={rootForm} layout="vertical" initialValues={{ source_type: 'wiki' }}>
          <Form.Item name="name" label="入口名称" rules={[{ required: true, message: '请输入入口名称' }]}><Input /></Form.Item>
          <Form.Item name="source_type" label="入口类型" rules={[{ required: true }]}><Select options={[{ label: moduleCode === 'energy' ? 'Wiki 根节点 / 电子表格' : 'Wiki 根节点', value: 'wiki' }, { label: '多维表格 Base', value: 'base' }]} /></Form.Item>
          <Form.Item name="source_url" label="完整链接或 Token" rules={[{ required: true, message: moduleCode === 'energy' ? '请输入 Wiki、电子表格或 Base 链接/Token' : '请输入 Wiki/Base 链接或 Token' }]}><Input /></Form.Item>
        </Form>
      </Modal>
    </main>
  )
}
