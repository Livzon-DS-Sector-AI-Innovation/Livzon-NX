'use client'

import { Card, Row, Col } from 'antd'
import {
  FileTextOutlined,
  FormOutlined,
  BookOutlined,
  CalendarOutlined,
  TeamOutlined,
  LineChartOutlined,
  UserAddOutlined,
  ProfileOutlined,
} from '@ant-design/icons'
import Link from 'next/link'

const modules = [
  {
    key: 'annual-plan',
    title: '年度培训计划',
    desc: '分为公司级和部门级，支持新建、编辑与导出',
    icon: <CalendarOutlined className="text-2xl text-[var(--color-primary)]" />,
    path: '/hr/training/annual-plan',
  },
  {
    key: 'sign-in',
    title: '培训资料',
    desc: '培训签到表、培训通知、培训评估表、口试/实操考核结果表',
    icon: <FormOutlined className="text-2xl text-[var(--color-primary)]" />,
    path: '/hr/training/sign-in',
  },
  {
    key: 'ledger',
    title: '培训台账',
    desc: '年度培训统计表，记录每次培训的详细信息',
    icon: <BookOutlined className="text-2xl text-[var(--color-primary)]" />,
    path: '/hr/training/ledger',
  },
  {
    key: 'employee-training-list',
    title: '员工培训清单',
    desc: '按人员汇总培训台账培训信息，支持配置与导出（HR-QD-01）',
    icon: <ProfileOutlined className="text-2xl text-[var(--color-primary)]" />,
    path: '/hr/training/employee-training-list',
  },
  {
    key: 'trainer',
    title: '培训师管理',
    desc: '管理企业内部培训师清单',
    icon: <TeamOutlined className="text-2xl text-[var(--color-primary)]" />,
    path: '/hr/training/trainer',
  },
  {
    key: 'position-training',
    title: '岗位培训清单',
    desc: '按部门和岗位管理培训教材清单',
    icon: <FileTextOutlined className="text-2xl text-[var(--color-primary)]" />,
    path: '/hr/training/position-training',
  },
  {
    key: 'plan-tracking',
    title: '培训计划跟踪',
    desc: '跟踪年度培训计划的执行情况',
    icon: <LineChartOutlined className="text-2xl text-[var(--color-primary)]" />,
    path: '/hr/training/plan-tracking',
  },
  {
    key: 'new-employee',
    title: '新员工培训',
    desc: '新员工入职培训计划与进度跟踪（按岗位培训清单生成）',
    icon: <UserAddOutlined className="text-2xl text-[var(--color-primary)]" />,
    path: '/hr/training/new-employee',
  },
]

export default function TrainingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
          培训管理
        </h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          员工培训相关业务管理（SMP-HR-002-14）
        </p>
      </div>

      <Row gutter={[16, 16]}>
        {modules.map((mod) => (
          <Col xs={24} sm={12} lg={8} key={mod.key}>
            <Link href={mod.path}>
              <Card
                hoverable
                className="h-full cursor-pointer transition-shadow hover:shadow-md"
              >
                <div className="flex items-start gap-4">
                  <div className="mt-1">{mod.icon}</div>
                  <div>
                    <h3 className="text-[16px] font-semibold text-[var(--color-charcoal)] mb-1">
                      {mod.title}
                    </h3>
                    <p className="text-[14px] text-[var(--color-steel)] leading-relaxed">
                      {mod.desc}
                    </p>
                  </div>
                </div>
              </Card>
            </Link>
          </Col>
        ))}
      </Row>
    </div>
  )
}
