'use client'

import { useState } from 'react'
import { Card, Typography, Divider, Tag, Row, Col, Input, Button, Table, Modal, Space } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { FundOutlined, ExperimentOutlined, SafetyOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography

interface IPCRecord {
  key: string
  罐号: string
  接种时间: string
  取样时间: string
  培养周期: string
  pH: string
  稀释倍数1: string
  测定结果: string
  残糖含量: string
  稀释倍数2: string
  吸光度值: string
  备注: string
}

const makeRow = (): IPCRecord => ({
  key: Date.now().toString(),
  罐号: '',
  接种时间: '',
  取样时间: '',
  培养周期: '',
  pH: '',
  稀释倍数1: '',
  测定结果: '',
  残糖含量: '',
  稀释倍数2: '',
  吸光度值: '',
  备注: '',
})

const IPC_COLUMNS: ColumnsType<IPCRecord> = [
  { title: '罐号', dataIndex: '罐号', width: 90, render: (v, _, i) => <Input size="small" value={v} data-index={i} data-field="罐号" /> },
  { title: '接种时间', dataIndex: '接种时间', width: 100, render: (v, _, i) => <Input size="small" value={v} data-index={i} data-field="接种时间" /> },
  { title: '取样时间', dataIndex: '取样时间', width: 90, render: (v, _, i) => <Input size="small" value={v} data-index={i} data-field="取样时间" /> },
  { title: '培养周期', dataIndex: '培养周期', width: 80, render: (v, _, i) => <Input size="small" value={v} data-index={i} data-field="培养周期" /> },
  { title: 'pH', dataIndex: 'pH', width: 70, render: (v, _, i) => <Input size="small" value={v} data-index={i} data-field="pH" /> },
  { title: '稀释倍数', dataIndex: '稀释倍数1', width: 80, render: (v, _, i) => <Input size="small" value={v} data-index={i} data-field="稀释倍数1" /> },
  { title: '测定结果', dataIndex: '测定结果', width: 90, render: (v, _, i) => <Input size="small" value={v} data-index={i} data-field="测定结果" /> },
  { title: '残糖含量', dataIndex: '残糖含量', width: 90, render: (v, _, i) => <Input size="small" value={v} data-index={i} data-field="残糖含量" /> },
  { title: '稀释倍数', dataIndex: '稀释倍数2', width: 80, render: (v, _, i) => <Input size="small" value={v} data-index={i} data-field="稀释倍数2" /> },
  { title: '吸光度值', dataIndex: '吸光度值', width: 90, render: (v, _, i) => <Input size="small" value={v} data-index={i} data-field="吸光度值" /> },
  { title: '备注', dataIndex: '备注', width: 120, render: (v, _, i) => <Input size="small" value={v} data-index={i} data-field="备注" /> },
]

const FieldRow = () => (
  <Row gutter={4} justify="space-between" style={{ textAlign: 'center', whiteSpace: 'pre-line', lineHeight: 1.6 }}>
    <Col flex="auto"><Text type="secondary">取样时间</Text></Col>
    <Col flex="auto"><Text type="secondary">{'培养周期\n（h）'}</Text></Col>
    <Col flex="auto"><Text type="secondary">pH</Text></Col>
    <Col flex="auto"><Text type="secondary">稀释倍数</Text></Col>
    <Col flex="auto"><Text type="secondary">测定结果</Text></Col>
    <Col flex="auto"><Text type="secondary">残糖含量</Text></Col>
    <Col flex="auto"><Text type="secondary">稀释倍数</Text></Col>
    <Col flex="auto"><Text type="secondary">吸光度值</Text></Col>
    <Col flex="auto"><Text type="secondary">备注</Text></Col>
  </Row>
)

const ExtraInfo = ({ onEnter }: { onEnter: () => void }) => (
  <Row gutter={12} align="middle" style={{ marginBottom: 8, fontSize: 13 }}>
    <Col><Text type="secondary" style={{ fontSize: 13 }}>罐号：</Text><Input size="small" style={{ width: 100 }} /></Col>
    <Col><Text type="secondary" style={{ fontSize: 13 }}>接种时间：</Text><Input size="small" style={{ width: 48 }} /> 年 <Input size="small" style={{ width: 48 }} /> 月 <Input size="small" style={{ width: 48 }} /> 日</Col>
    <Col><Button size="small" icon={<PlusOutlined />} onClick={onEnter}>录入数据</Button></Col>
  </Row>
)

export default function QualityPage() {
  const [seedData, setSeedData] = useState<IPCRecord[]>([makeRow()])
  const [fermentData, setFermentData] = useState<IPCRecord[]>([makeRow()])
  const [seedVisible, setSeedVisible] = useState(false)
  const [fermentVisible, setFermentVisible] = useState(false)

  const handleCellChange = (setter: React.Dispatch<React.SetStateAction<IPCRecord[]>>, index: number, field: keyof IPCRecord, value: string) => {
    setter(prev => prev.map((r, i) => i === index ? { ...r, [field]: value } : r))
  }

  const navigateCell = (current: HTMLElement, direction: 'up' | 'down' | 'left' | 'right') => {
    const td = current.closest('td')
    const row = td?.closest('tr') as HTMLTableRowElement | null
    if (!row) return
    const cells = Array.from(row.querySelectorAll('td'))
    const colIdx = cells.indexOf(current.closest('td')!)
    let targetRow: HTMLTableRowElement | null = row
    if (direction === 'down') targetRow = row.nextElementSibling as HTMLTableRowElement | null
    if (direction === 'up') targetRow = row.previousElementSibling as HTMLTableRowElement | null
    if (!targetRow) return
    const targetCells = Array.from(targetRow.querySelectorAll('td'))
    const targetCol = direction === 'left' ? Math.max(0, colIdx - 1) : direction === 'right' ? Math.min(cells.length - 1, colIdx + 1) : colIdx
    const targetInput = targetCells[targetCol]?.querySelector('input')
    if (targetInput) { targetInput.focus(); targetInput.select() }
  }

  const handleCellKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    const map: Record<string, 'up' | 'down' | 'left' | 'right'> = {
      ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
    }
    if (e.key === 'Enter') { e.preventDefault(); navigateCell(e.currentTarget, 'down') }
    if (e.key === 'Tab' && !e.shiftKey) { e.preventDefault(); navigateCell(e.currentTarget, 'right') }
    if (e.key === 'Tab' && e.shiftKey) { e.preventDefault(); navigateCell(e.currentTarget, 'left') }
    const dir = map[e.key]
    if (dir) { e.preventDefault(); navigateCell(e.currentTarget, dir) }
  }

  const addRow = (setter: React.Dispatch<React.SetStateAction<IPCRecord[]>>) => setter(prev => [...prev, makeRow()])
  const deleteRow = (setter: React.Dispatch<React.SetStateAction<IPCRecord[]>>, key: string) => setter(prev => prev.filter(r => r.key !== key))

  const makeDisplayColumns = (): ColumnsType<IPCRecord> => [
    { title: '罐号', dataIndex: '罐号', width: 90 },
    { title: '接种时间', dataIndex: '接种时间', width: 100 },
    { title: '取样时间', dataIndex: '取样时间', width: 90 },
    { title: '培养周期', dataIndex: '培养周期', width: 80 },
    { title: 'pH', dataIndex: 'pH', width: 70 },
    { title: '稀释倍数', dataIndex: '稀释倍数1', width: 80 },
    { title: '测定结果', dataIndex: '测定结果', width: 90 },
    { title: '残糖含量', dataIndex: '残糖含量', width: 90 },
    { title: '稀释倍数', dataIndex: '稀释倍数2', width: 80 },
    { title: '吸光度值', dataIndex: '吸光度值', width: 90 },
    { title: '备注', dataIndex: '备注', width: 100 },
  ]

  const makeColumns = (setter: React.Dispatch<React.SetStateAction<IPCRecord[]>>): ColumnsType<IPCRecord> => [
    { title: '罐号', width: 90, render: (_, r, i) => <Input size="small" value={r.罐号} onChange={e => handleCellChange(setter, i, '罐号', e.target.value)} onKeyDown={handleCellKeyDown} /> },
    { title: '接种时间', width: 100, render: (_, r, i) => <Input size="small" value={r.接种时间} onChange={e => handleCellChange(setter, i, '接种时间', e.target.value)} /> },
    { title: '取样时间', width: 90, render: (_, r, i) => <Input size="small" value={r.取样时间} onChange={e => handleCellChange(setter, i, '取样时间', e.target.value)} /> },
    { title: '培养周期', width: 80, render: (_, r, i) => <Input size="small" value={r.培养周期} onChange={e => handleCellChange(setter, i, '培养周期', e.target.value)} /> },
    { title: 'pH', width: 70, render: (_, r, i) => <Input size="small" value={r.pH} onChange={e => handleCellChange(setter, i, 'pH', e.target.value)} /> },
    { title: '稀释倍数', width: 80, render: (_, r, i) => <Input size="small" value={r.稀释倍数1} onChange={e => handleCellChange(setter, i, '稀释倍数1', e.target.value)} /> },
    { title: '测定结果', width: 90, render: (_, r, i) => <Input size="small" value={r.测定结果} onChange={e => handleCellChange(setter, i, '测定结果', e.target.value)} /> },
    { title: '残糖含量', width: 90, render: (_, r, i) => <Input size="small" value={r.残糖含量} onChange={e => handleCellChange(setter, i, '残糖含量', e.target.value)} /> },
    { title: '稀释倍数', width: 80, render: (_, r, i) => <Input size="small" value={r.稀释倍数2} onChange={e => handleCellChange(setter, i, '稀释倍数2', e.target.value)} /> },
    { title: '吸光度值', width: 90, render: (_, r, i) => <Input size="small" value={r.吸光度值} onChange={e => handleCellChange(setter, i, '吸光度值', e.target.value)} /> },
    { title: '备注', width: 100, render: (_, r, i) => <Input size="small" value={r.备注} onChange={e => handleCellChange(setter, i, '备注', e.target.value)} /> },
    { title: '操作', width: 60, fixed: 'right', render: (_, r) => <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteRow(setter, r.key)} /> },
  ]

  return (
    <div className="p-6">
      <Title level={4}><FundOutlined className="mr-2" />中间体质控数据台账</Title>
      <Text type="secondary">从飞书同步中控化验数据</Text>

      <Divider />

      <Card title={<span><ExperimentOutlined className="mr-2" />IPC（过程化验）指标录入</span>}>
        <Paragraph className="mt-3">
          <Text strong>定位：</Text>
          <Text type="secondary">供化验员或工艺员手动录入的过程化验数据</Text>
        </Paragraph>
        <Paragraph className="mt-2">
          <Text strong>AI 价值：</Text>
          <Text type="secondary">AI 后台计算动态斜率，用于预测动态放罐时间和染菌早期预警</Text>
        </Paragraph>

        <Divider plain style={{ fontSize: 14 }}>种子</Divider>
        <ExtraInfo onEnter={() => setSeedVisible(true)} />
        <FieldRow />
        {seedData.length > 0 && seedData[0].罐号 && (
          <Table className="mt-2" columns={makeDisplayColumns()} dataSource={seedData} pagination={false} size="small" scroll={{ x: 1200 }} />
        )}
        <div style={{ marginTop: 120 }} />

        <Divider plain style={{ fontSize: 14 }}>发酵</Divider>
        <ExtraInfo onEnter={() => setFermentVisible(true)} />
        <FieldRow />
        {fermentData.length > 0 && fermentData[0].罐号 && (
          <Table className="mt-2" columns={makeDisplayColumns()} dataSource={fermentData} pagination={false} size="small" scroll={{ x: 1200 }} />
        )}      </Card>

      <Card className="mt-4" title={<span><SafetyOutlined className="mr-2" />无菌镜检</span>}>
        <Row gutter={24}>
          <Col span={12}>
            <Text strong style={{ fontSize: 14 }}>镜检情况</Text>
            <Input.TextArea
              rows={14}
              style={{ marginTop: 8, fontFamily: 'monospace', fontSize: 13 }}
              placeholder={`FA:
202A-26183批，移前平板外观正常，涂片正常
...

LV:
401B-26027批，移前摇瓶涂片正常
...`}
            />
          </Col>
          <Col span={12}>
            <Text strong style={{ fontSize: 14 }}>AI 归档总结</Text>
            <Tag color="default" className="ml-2">待开发</Tag>
            <Paragraph className="mt-3" type="secondary">AI 自动分析镜检结果，生成趋势报告和染菌预警归档</Paragraph>
            <ul style={{ color: '#666', lineHeight: 2.2 }}>
              <li>批次镜检统计</li>
              <li>染菌率趋势</li>
              <li>异常批次标记</li>
              <li>放行建议</li>
            </ul>
          </Col>
        </Row>
      </Card>

      {/* 种子数据录入 Modal */}
      <Modal title="种子 · IPC 数据录入" open={seedVisible} onCancel={() => setSeedVisible(false)} width="100%" style={{ top: 20, maxWidth: 1400 }}
        footer={[
          <Button key="add" icon={<PlusOutlined />} onClick={() => addRow(setSeedData)}>新增行</Button>,
          <Button key="cancel" onClick={() => setSeedVisible(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => setSeedVisible(false)}>保存</Button>,
        ]}>
        <Table columns={makeColumns(setSeedData)} dataSource={seedData} pagination={false} size="small" scroll={{ x: 1200 }} />
      </Modal>

      {/* 发酵数据录入 Modal */}
      <Modal title="发酵 · IPC 数据录入" open={fermentVisible} onCancel={() => setFermentVisible(false)} width="100%" style={{ top: 20, maxWidth: 1400 }}
        footer={[
          <Button key="add" icon={<PlusOutlined />} onClick={() => addRow(setFermentData)}>新增行</Button>,
          <Button key="cancel" onClick={() => setFermentVisible(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={() => setFermentVisible(false)}>保存</Button>,
        ]}>
        <Table columns={makeColumns(setFermentData)} dataSource={fermentData} pagination={false} size="small" scroll={{ x: 1200 }} />
      </Modal>
    </div>
  )
}
