'use client'

import { useCallback, useEffect, useState } from 'react'
import { Button, Card, Col, Row, Select, Space, Statistic, Table, Tabs, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined } from '@ant-design/icons'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { getAgentModuleCoverage, type AgentModuleCoverage, type AgentModuleCoverageView } from '@/actions/settings'

const states = { not_integrated: '未接入', partial: '部分覆盖', integrated: '页面已覆盖', disabled: '全部停用' }
const toolStates = { enabled: '已启用', disabled: '已停用', excluded: '未开放' }
const percent = (value: number | null) => value == null ? '不适用' : `${value}%`

function ModuleDetails({ moduleInfo }: { moduleInfo: AgentModuleCoverage }) {
  const [onlyMissing, setOnlyMissing] = useState(false)
  return <Tabs items={[
    { key: 'pages', label: '页面覆盖', children: <>
      <Select aria-label="页面覆盖筛选" className="mb-3 min-w-40" value={onlyMissing ? 'missing' : 'all'}
        onChange={(value) => setOnlyMissing(value === 'missing')}
        options={[{ value: 'all', label: '全部业务页面' }, { value: 'missing', label: '仅看未覆盖页面' }]} />
      <Table rowKey="page_key" size="small" dataSource={moduleInfo.pages.filter((page) => !onlyMissing || page.registered_count === 0)}
        pagination={{ pageSize: 10, showSizeChanger: false }} scroll={{ x: 650 }}
        locale={{ emptyText: onlyMissing ? '没有未覆盖页面' : '该模块暂无有效业务页面' }} columns={[
          { title: '业务页面', dataIndex: 'page_name' },
          { title: '页面路径', dataIndex: 'route_path', ellipsis: true },
          { title: '注册工具', dataIndex: 'registered_count', width: 100 },
          { title: '启用工具', dataIndex: 'enabled_count', width: 100 },
          { title: '接入状态', width: 120, render: (_, page) => <Tag>{page.registered_count === 0 ? '未覆盖' : page.enabled_count === 0 ? '已停用' : '已覆盖'}</Tag> },
        ]} />
    </> },
    { key: 'tools', label: '工具明细', children: <Table rowKey="operation" size="small" dataSource={moduleInfo.tools}
      pagination={{ pageSize: 10, showSizeChanger: false }} scroll={{ x: 700 }} locale={{ emptyText: '该模块尚未声明工具' }} columns={[
        { title: '业务能力', dataIndex: 'summary' },
        { title: '操作标识', dataIndex: 'operation', ellipsis: true },
        { title: '状态', dataIndex: 'state', width: 100, render: (state: keyof typeof toolStates) => <Tag>{toolStates[state]}</Tag> },
        { title: '执行方式', width: 140, render: (_, tool) => tool.human_decision_required ? '需人工处理' : tool.write ? '确认后写入' : '查询' },
        { title: '未开放原因', dataIndex: 'reason', render: (reason: string | null) => reason || '—' },
      ]} /> },
  ]} />
}

export default function AgentModuleCoverageClient() {
  const [data, setData] = useState<AgentModuleCoverageView | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [state, setState] = useState<string>('all')
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try { setData(await getAgentModuleCoverage()) }
    catch (cause) { setData(null); setError(cause instanceof Error ? cause.message : '模块接入情况读取失败') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])
  const columns: ColumnsType<AgentModuleCoverage> = [
    { title: '业务模块', dataIndex: 'module_name', width: 130 },
    { title: '接入状态', dataIndex: 'state', width: 130, render: (value: keyof typeof states) => <Tag>{states[value]}</Tag> },
    { title: '覆盖率', dataIndex: 'coverage_percent', width: 100, render: percent },
    { title: '页面覆盖', width: 120, render: (_, item) => `${item.covered_pages}/${item.total_pages}` },
    { title: '注册工具', dataIndex: 'registered_count', width: 100 },
    { title: '启用工具', dataIndex: 'enabled_count', width: 100 },
    { title: '未开放工具', dataIndex: 'excluded_count', width: 110 },
    { title: '当前启用页面', dataIndex: 'enabled_pages', width: 130 },
  ]
  return <Space orientation="vertical" size={16} className="w-full">
    <PlatformNotice type="info" title="覆盖率按业务页面的工具绑定统计，不代表页面全部功能均可由助手执行。"
      description="分母为平台当前有效业务页面，分子为至少绑定一个已注册工具的页面，重复绑定只计一次。停用工具仍计入注册覆盖，当前启用页面另列。系统设置不计入业务覆盖率；个人基础工具单列。工具启用不替代用户角色授权，审批、驳回等责任操作仍需人工处理。" />
    {error && <PlatformNotice type="error" title="模块接入情况读取失败" description={error} action={<Button onClick={() => void load()}>重试</Button>} />}
    {data && <Row gutter={[16, 16]}>
      <Col xs={24} sm={12} lg={6}><Card className="h-full"><Statistic title="已接入模块" value={`${data.modules.filter((item) => item.registered_count > 0).length}/${data.modules.length}`} /></Card></Col>
      <Col xs={24} sm={12} lg={6}><Card className="h-full"><Statistic title="已注册工具（含个人基础）" value={data.registered_count} /><div>当前启用 {data.enabled_count} 项</div></Card></Col>
      <Col xs={24} sm={12} lg={6}><Card className="h-full"><Statistic title="业务页面覆盖率" value={percent(data.coverage_percent ?? null)} /><div>{data.covered_pages}/{data.total_pages} 页 · 当前启用 {data.enabled_pages} 页</div></Card></Col>
      <Col xs={24} sm={12} lg={6}><Card className="h-full"><Statistic title="未开放工具（含设置类）" value={data.excluded_count} /><div>个人基础工具 {data.personal_count} 项</div></Card></Col>
    </Row>}
    <Card title="模块能力接入" extra={<Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新接入情况</Button>}>
      <Select aria-label="模块接入状态筛选" className="mb-4 min-w-40" value={state} onChange={setState}
        options={[{ value: 'all', label: '全部模块' }, ...Object.entries(states).map(([value, label]) => ({ value, label }))]} />
      {data && <div className="mb-3 text-xs text-[var(--color-text-secondary)]">统计时间：{new Date(data.generated_at).toLocaleString()}；展开模块查看页面缺口和工具明细。</div>}
      <Table rowKey="module_code" columns={columns} loading={loading} scroll={{ x: 1020 }} pagination={false}
        dataSource={data?.modules.filter((item) => state === 'all' || item.state === state) ?? []}
        locale={{ emptyText: error ? '读取失败，请重试' : '暂无符合条件的模块' }}
        expandable={{ expandedRowRender: (item) => <ModuleDetails moduleInfo={item} /> }} />
    </Card>
  </Space>
}
