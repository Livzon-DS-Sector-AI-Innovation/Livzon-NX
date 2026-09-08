import { describe, it, expect } from 'vitest'
import {
  buildNameCounts,
  memberOptionValue,
  memberOptionLabel,
  resolvePersonnelValue,
  itemToOptionValue,
} from './TrainingPersonnelConfigModal'
import type { TrainingPersonnelItem } from '@/types/hr'

// 与弹窗内部一致的测试用成员形状（Member 未对外导出，此处以结构化类型传入）
type Member = { name: string; employee_no?: string }

// ── 重名不去重：班组合并 / 拉取新员工语义（与组件内逻辑等价） ──

/** 多选班组加载语义：选中班组人员不去重，直接拼接 */
function mergeSelectedConfigs(configs: { personnel: TrainingPersonnelItem[] }[]): TrainingPersonnelItem[] {
  return configs.flatMap((c) => c.personnel || [])
}

/** 拉取新员工语义：现有名单 + 新员工不去重，全部追加 */
function appendNewHires(
  existingNames: string[],
  deptMap: Record<string, string>,
  newItems: TrainingPersonnelItem[],
): TrainingPersonnelItem[] {
  return [
    ...existingNames.map((name) => ({ name, department: deptMap[name] })),
    ...newItems,
  ]
}

describe('培训签到表重名不去重', () => {
  it('多选班组：两个班组各含同名同部门不同工号的人，两条全保留', () => {
    const merged = mergeSelectedConfigs([
      { personnel: [{ name: '张三', department: '仪器组', employee_number: '0023' }] },
      { personnel: [{ name: '张三', department: '仪器组', employee_number: '0157' }] },
    ])
    expect(merged).toHaveLength(2)
    expect(merged.map((m) => m.employee_number)).toEqual(['0023', '0157'])
  })

  it('拉取新员工：与现有名单重名的新员工不被过滤', () => {
    const merged = appendNewHires(
      ['张三', '李四'],
      { 张三: '仪器组', 李四: '合成组' },
      [{ name: '张三', department: '前处理组', employee_number: '9527' }],
    )
    expect(merged.map((m) => m.name)).toEqual(['张三', '李四', '张三'])
    expect(merged[2].employee_number).toBe('9527')
  })

  it('拉取新员工：与现有同名同部门也不去重', () => {
    const merged = appendNewHires(
      ['张三'],
      { 张三: '仪器组' },
      [{ name: '张三', department: '仪器组' }],
    )
    expect(merged).toHaveLength(2)
  })
})

// ── 弹窗 option 唯一 value / 纯姓名 label / 编解码往返 ──

describe('班组人员配置弹窗 - 重名选择支持', () => {
  it('同名同部门：两条选项的 value 互不相同，但 label 都是纯姓名', () => {
    const members: Member[] = [
      { name: '张三', employee_no: '0023' },
      { name: '张三', employee_no: '0157' },
    ]
    const v0 = memberOptionValue(members, 0)
    const v1 = memberOptionValue(members, 1)
    expect(v0).not.toBe(v1)
    expect(memberOptionLabel({ name: '张三', employee_no: '0023' })).toBe('张三')
    expect(v0).toContain('张三')
    // 工号仅作内部 value，label 不得出现工号
    expect(memberOptionLabel(members[0])).not.toContain('0023')
  })

  it('不重名时 value 即纯姓名', () => {
    const members: Member[] = [{ name: '王五', employee_no: '0001' }]
    expect(memberOptionValue(members, 0)).toBe('王五')
  })

  it('同名且都无工号：用 #序号 后缀兜底，两条 value 仍互异', () => {
    const members: Member[] = [{ name: '赵六' }, { name: '赵六' }]
    const v0 = memberOptionValue(members, 0)
    const v1 = memberOptionValue(members, 1)
    expect(v0).not.toBe(v1)
    expect(v0).toContain('赵六')
    expect(v1).toContain('赵六')
  })

  it('buildNameCounts 统计同名人数', () => {
    const counts = buildNameCounts([
      { name: '张三' },
      { name: '李四' },
      { name: '张三' },
    ])
    expect(counts.get('张三')).toBe(2)
    expect(counts.get('李四')).toBe(1)
  })

  it('resolvePersonnelValue：成员选项解析为 name+employee_number，手动姓名原样', () => {
    const members: Member[] = [
      { name: '张三', employee_no: '0023' },
      { name: '张三', employee_no: '0157' },
    ]
    const prev: TrainingPersonnelItem[] = []
    const resolved = resolvePersonnelValue(memberOptionValue(members, 1), members, prev, '仪器组')
    expect(resolved).toEqual({ name: '张三', employee_number: '0157', department: '仪器组' })

    // 手动输入姓名（不在候选人里）按纯姓名保留
    const manual = resolvePersonnelValue('临时工', [], prev, '仪器组')
    expect(manual).toEqual({ name: '临时工', department: '仪器组' })
  })

  it('itemToOptionValue 与 resolvePersonnelValue 编解码往返一致（含同名无工号）', () => {
    const members: Member[] = [{ name: '赵六' }, { name: '赵六' }]
    const item0: TrainingPersonnelItem = { name: '赵六', employee_number: undefined, department: '仪器组' }
    const v0 = itemToOptionValue(item0, members, 0)
    const v1 = itemToOptionValue(item0, members, 1)
    expect(v0).not.toBe(v1)
    // 解码回 name 仍是纯姓名
    expect(resolvePersonnelValue(v0, members, [], '仪器组').name).toBe('赵六')
    expect(resolvePersonnelValue(v1, members, [], '仪器组').name).toBe('赵六')
  })
})
