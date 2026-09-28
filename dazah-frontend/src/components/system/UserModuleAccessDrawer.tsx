'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ComponentRef } from 'react'
import { App, Button, Checkbox, Drawer, Empty, Input, Skeleton, Table, Tag, Typography } from 'antd'
import Alert from '@/components/shared/PlatformNotice'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { getUserModulePermissions, replaceUserModulePermissions } from '@/actions/users'
import { moduleMenus } from '@/lib/menu-config'
import type {
  ModulePermissionDefinitionOut,
  ModulePermissionGrantInput,
  ModulePermissionKey,
  UserModulePermissionsOut,
} from '@/actions/users'
import styles from './UserModuleAccessDrawer.module.css'

const { Text, Title } = Typography
const navigationModuleCodes = new Set(moduleMenus.map((module) => module.moduleCode))

export interface ModuleAccessUser {
  id: string
  name: string
  isSystemAdmin: boolean
}

function selectedModuleCodes(result: UserModulePermissionsOut): string[] {
  return (result.grants || [])
    .filter((grant) => (grant.permissions || []).includes('module.view'))
    .map((grant) => grant.module_code)
    .sort()
}

function sameSelection(left: string[], right: string[]) {
  return [...left].sort().join('\0') === [...right].sort().join('\0')
}

export default function UserModuleAccessDrawer({
  user,
  open,
  onClose,
}: {
  user: ModuleAccessUser | null
  open: boolean
  onClose: () => void
}) {
  const { message, modal } = App.useApp()
  const sessionVersion = useRef(0)
  const reasonInputRef = useRef<ComponentRef<typeof Input.TextArea>>(null)
  const userId = user?.id
  const [result, setResult] = useState<UserModulePermissionsOut | null>(null)
  const [selectedCodes, setSelectedCodes] = useState<string[]>([])
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState(false)
  const [moduleSearch, setModuleSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  const load = useCallback(async () => {
    if (!userId) return
    const version = ++sessionVersion.current
    setLoading(true)
    setSaving(false)
    setResult(null)
    setReason('')
    setReasonError(false)
    setModuleSearch('')
    setErrorMessage('')
    try {
      const next = await getUserModulePermissions(userId)
      if (version !== sessionVersion.current) return
      if (next.user_id !== userId) throw new Error('用户授权返回对象不一致，请重新加载')
      setResult(next)
      setSelectedCodes(selectedModuleCodes(next))
    } catch (error) {
      if (version !== sessionVersion.current) return
      setErrorMessage(error instanceof Error ? error.message : '加载模块访问权限失败')
    } finally {
      if (version === sessionVersion.current) setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    if (!open) return
    const timeoutId = window.setTimeout(() => void load(), 0)
    return () => {
      window.clearTimeout(timeoutId)
      sessionVersion.current += 1
    }
  }, [load, open])

  const originalCodes = useMemo(() => result ? selectedModuleCodes(result) : [], [result])
  const availableModules = useMemo(
    () => (result?.available_modules || []).filter((module) => navigationModuleCodes.has(module.module_code)),
    [result],
  )
  const availableModuleCodes = useMemo(
    () => new Set(availableModules.map((module) => module.module_code)),
    [availableModules],
  )
  const changed = !sameSelection(originalCodes, selectedCodes)
  const selected = useMemo(() => new Set(selectedCodes), [selectedCodes])
  const visibleSelectedCount = availableModules.filter((module) => selected.has(module.module_code)).length
  const filteredModules = useMemo(() => {
    const keyword = moduleSearch.trim().toLocaleLowerCase()
    return availableModules.filter((module) => !keyword ||
      [module.module_name, module.module_code, module.description || '']
        .some((value) => value.toLocaleLowerCase().includes(keyword)))
  }, [availableModules, moduleSearch])
  const addedModules = availableModules.filter((module) => selected.has(module.module_code) && !originalCodes.includes(module.module_code))
  const removedModules = availableModules.filter((module) => !selected.has(module.module_code) && originalCodes.includes(module.module_code))
  const ready = Boolean(result && result.user_id === userId && !loading)
  const editable = ready && !saving && !user?.isSystemAdmin

  const setModuleAccess = (moduleCode: string, allowed: boolean) => {
    setSelectedCodes((current) => {
      const next = new Set(current)
      if (allowed) next.add(moduleCode)
      else next.delete(moduleCode)
      return [...next].sort()
    })
  }

  const close = () => {
    if (saving) return
    if (!changed && !reason.trim()) return onClose()
    const version = sessionVersion.current
    modal.confirm({
      title: '放弃未保存的模块访问调整？',
      centered: true,
      icon: null,
      content: <Alert type="warning" showIcon title="关闭后，本次模块访问调整和授权原因将丢失。" />,
      okText: '放弃更改',
      cancelText: '继续编辑',
      onOk: () => {
        if (version === sessionVersion.current) onClose()
      },
    })
  }

  const refresh = () => {
    if (saving) return
    if (!changed && !reason.trim()) { void load(); return }
    const version = sessionVersion.current
    modal.confirm({
      title: '重新加载模块访问权限？',
      centered: true,
      icon: null,
      content: <Alert type="warning" showIcon title="重新加载将放弃未保存的模块访问调整和授权原因。" />,
      okText: '放弃并刷新',
      cancelText: '继续编辑',
      onOk: () => { if (version === sessionVersion.current) return load() },
    })
  }

  const save = async () => {
    if (!user || !result || result.user_id !== user.id || !open || saving || loading || user.isSystemAdmin) return
    if (!reason.trim()) {
      setReasonError(true)
      reasonInputRef.current?.focus()
      message.warning('请填写本次模块访问调整原因')
      return
    }
    const version = sessionVersion.current
    const grantByModule = new Map((result.grants || []).map((grant) => [grant.module_code, grant]))
    const grants: ModulePermissionGrantInput[] = selectedCodes.map((moduleCode) => {
      const current = grantByModule.get(moduleCode)
      const permissions = new Set<ModulePermissionKey>(current?.permissions || [])
      permissions.add('module.view')
      return {
        module_code: moduleCode,
        permissions: [...permissions].sort(),
        data_scope: current?.data_scope || {},
      }
    })
    try {
      setSaving(true)
      const next = await replaceUserModulePermissions(user.id, {
        expected_grant_version: result.grant_version,
        grants,
        reason: reason.trim(),
      })
      if (version !== sessionVersion.current) return
      if (next.user_id !== user.id) throw new Error('用户授权返回对象不一致，请重新加载')
      setResult(next)
      setSelectedCodes(selectedModuleCodes(next))
      setReason('')
      setReasonError(false)
      setErrorMessage('')
      message.success('模块访问权限已保存并生效')
    } catch (error) {
      if (version !== sessionVersion.current) return
      setErrorMessage(`${error instanceof Error ? error.message : '保存模块访问权限失败'}。本地修改已保留，请核对后重试。`)
    } finally {
      if (version === sessionVersion.current) setSaving(false)
    }
  }

  const permissionSummary = <div className={styles.previewContent}>
    <Alert type={removedModules.length ? 'warning' : 'info'} showIcon
      title={`将新增 ${addedModules.length} 个模块访问入口，移除 ${removedModules.length} 个模块访问入口。`}
      description="关闭模块后，用户将无法进入对应模块；模块内页面权限仍按现有角色与用户页面配置生效。" />
    <div><Text strong>允许访问：</Text>
      {availableModules.filter((module) => user?.isSystemAdmin || selected.has(module.module_code))
        .map((module) => <Tag key={module.module_code}>{module.module_name}</Tag>)}
      {!user?.isSystemAdmin && !visibleSelectedCount && <Text type="secondary">未允许任何业务模块</Text>}
    </div>
    {!!addedModules.length && <div><Text strong>新增入口：</Text>
      {addedModules.map((module) => <Tag color="green" key={module.module_code}>{module.module_name}</Tag>)}
    </div>}
    {!!removedModules.length && <div><Text strong>关闭入口：</Text>
      {removedModules.map((module) => <Tag color="red" key={module.module_code}>{module.module_name}</Tag>)}
    </div>}
  </div>

  const showAccessRules = () => modal.info({
    title: '模块访问与页面权限规则',
    centered: true,
    width: 640,
    icon: null,
    okText: '我知道了',
    content: <div>
      <Text strong>模块控制访问入口，角色提供页面和操作权限基线。</Text>
      <p>允许访问模块后，具体页面和操作权限仍按已分配角色及用户页面配置生效；允许访问模块不会自动授予全部页面和操作权限。关闭模块后，用户将无法进入对应模块。系统管理员默认拥有全部模块访问权限，不能在此限制。</p>
    </div>,
  })

  const previewPermissions = () => {
    if (!ready || saving) return
    modal.info({
      title: `${user?.name || '用户'} · 模块访问配置预览`,
      centered: true,
      width: 640,
      icon: null,
      okText: '返回编辑',
      content: permissionSummary,
    })
  }

  const previewSave = () => {
    if (!editable) return
    if (!changed) {
      message.info('没有需要保存的模块访问调整')
      return
    }
    if (!reason.trim()) {
      setReasonError(true)
      reasonInputRef.current?.focus()
      message.warning('请填写本次模块访问调整原因')
      return
    }
    const version = sessionVersion.current
    modal.confirm({
      title: `确认调整${user?.name || '用户'}的模块访问权限`,
      centered: true,
      width: 640,
      icon: null,
      content: <div className={styles.previewContent}>
        {permissionSummary}
        <div><Text strong>授权调整原因：</Text>{reason.trim()}</div>
      </div>,
      okText: '确认保存',
      cancelText: '返回修改',
      onOk: () => {
        if (version === sessionVersion.current) return save()
      },
    })
  }

  const columns = [
    {
      title: '模块',
      key: 'module',
      render: (_: unknown, module: ModulePermissionDefinitionOut) => (
        <div className={styles.moduleDescription}>
          <Text strong>{module.module_name}</Text>
          <Text type="secondary" className={styles.description}>{module.description}</Text>
        </div>
      ),
    },
    {
      title: '访问状态',
      key: 'access',
      width: 124,
      render: (_: unknown, module: ModulePermissionDefinitionOut) => (
        <Checkbox
          checked={user?.isSystemAdmin || selected.has(module.module_code)}
          disabled={!editable}
          aria-label={`${module.module_name}模块访问`}
          onChange={(event) => setModuleAccess(module.module_code, event.target.checked)}
        >
          {user?.isSystemAdmin || selected.has(module.module_code) ? '允许访问' : '禁止访问'}
        </Checkbox>
      ),
    },
  ]

  return (
    <Drawer
      rootClassName={styles.drawer}
      title={<div>
        <Title level={4} className={styles.title}>模块访问 · {user?.name || '用户'}</Title>
        <Text type="secondary" className={styles.subtitle}>配置账号可进入的业务模块</Text>
      </div>}
      extra={<Button icon={<ReloadOutlined />} loading={loading} disabled={saving} onClick={refresh}>刷新</Button>}
      open={open}
      onClose={close}
      placement="right"
      closable={!saving}
      mask={{ closable: !saving }}
      size="min(820px, 100vw)"
      destroyOnHidden
      footer={(
        <div className={styles.footer}>
          <Button disabled={saving} onClick={close}>取消</Button>
          <Button className={styles.previewButton} disabled={!ready || saving} onClick={previewPermissions}>预览权限</Button>
          <Button
            type="primary"
            loading={saving}
            disabled={!editable || !changed}
            onClick={previewSave}
          >
            保存
          </Button>
        </div>
      )}
    >
      <div className={styles.body}>
        <Alert className={styles.rulesNotice} type="info" showIcon title="模块控制访问入口，角色提供页面和操作权限基线。"
          rulesDisabled={saving} onLearnRules={showAccessRules} />
        {ready && result && <div className={styles.summary}>
          <div className={styles.selectionSummary}>
            <Text strong>已允许 {user?.isSystemAdmin ? availableModules.length : visibleSelectedCount} 个模块</Text>
            <Text type="secondary">共 {availableModules.length} 个可配置模块</Text>
          </div>
          <div className={styles.summaryDetails}>
            {!!addedModules.length && !user?.isSystemAdmin && <Tag color="green">新增 {addedModules.length}</Tag>}
            {!!removedModules.length && !user?.isSystemAdmin && <Tag color="red">关闭 {removedModules.length}</Tag>}
            <Text type="secondary">授权版本 {result.grant_version}</Text>
          </div>
        </div>}

        {user?.isSystemAdmin && (
          <Alert
            type="info"
            showIcon
            title="系统管理员默认拥有全部模块访问权限，不能在此限制。"
          />
        )}
        {result?.livzon_sync_status === 'failed' && (
          <Alert
            type="warning"
            showIcon
            title="模块访问已保存，但 Livzon 范围同步失败"
            description={result.livzon_last_error || '请检查能力注册状态后重试。'}
          />
        )}
        {errorMessage && (
          <Alert
            type="error"
            showIcon
            title={errorMessage}
            action={<Button size="small" disabled={loading || saving} onClick={ready ? previewSave : refresh}>
              {ready ? '重试保存' : '重新加载'}
            </Button>}
          />
        )}

        {loading || (open && userId && !ready && !errorMessage) ? (
          <Skeleton active paragraph={{ rows: 8 }} />
        ) : availableModules.length ? (
          <section aria-label="模块访问配置">
            <div className={styles.sectionHeading}>
              <Title level={5}>业务模块</Title>
              <Text type="secondary">允许访问的模块将显示在用户导航中</Text>
            </div>
            <div className={styles.toolbar}>
              <Input prefix={<SearchOutlined />} allowClear value={moduleSearch}
                onChange={(event) => setModuleSearch(event.target.value)} disabled={saving}
                placeholder="搜索模块名称或编码" aria-label="搜索模块" className={styles.search} />
              <div className={styles.batchActions}>
                <Button
                  disabled={!editable}
                  onClick={() => setSelectedCodes((current) => [...new Set([
                    ...current,
                    ...availableModules.map((module) => module.module_code),
                  ])].sort())}
                >
                  全部允许
                </Button>
                <Button
                  danger
                  disabled={!editable}
                  onClick={() => setSelectedCodes((current) => current.filter((code) => !availableModuleCodes.has(code)))}
                >
                  全部关闭
                </Button>
              </div>
            </div>
            {!!moduleSearch.trim() && <Text type="secondary" className={styles.searchHelp}>
              当前显示 {filteredModules.length} 个模块；批量操作适用于全部 {availableModules.length} 个可配置模块。
            </Text>}
            <Table
              className={styles.moduleTable}
              rowKey="module_code"
              columns={columns}
              dataSource={filteredModules}
              rowClassName={(module) => user?.isSystemAdmin || selected.has(module.module_code) ? styles.allowedRow : ''}
              pagination={false}
              size="middle"
              tableLayout="fixed"
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的模块，请调整搜索条件。" /> }}
            />
          </section>
        ) : (
          ready && !errorMessage && <Empty description="暂无可配置的业务模块，请检查模块注册与导航配置。" />
        )}
        <section>
          <label htmlFor="module-access-reason" className={styles.reasonLabel}>授权调整原因<Text type="secondary">（保存时必填）</Text></label>
          <Input.TextArea ref={reasonInputRef} id="module-access-reason" aria-label="模块访问调整原因" value={reason}
            aria-required aria-invalid={reasonError} aria-describedby={reasonError ? 'module-access-reason-error' : undefined}
            status={reasonError ? 'error' : undefined}
            onChange={(event) => { setReason(event.target.value); if (event.target.value.trim()) setReasonError(false) }} placeholder="填写模块访问调整原因"
            maxLength={500} showCount autoSize={{ minRows: 2, maxRows: 4 }} disabled={!editable} />
          {reasonError && <Text type="danger" id="module-access-reason-error" className={styles.reasonError}>请填写本次模块访问调整原因</Text>}
        </section>
      </div>
    </Drawer>
  )
}
