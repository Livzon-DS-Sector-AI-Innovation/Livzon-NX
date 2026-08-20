'use client'
import {Result,} from 'antd'

export default function Page() {
  return (
    <Result
      status="info"
      title="203 车间 — 数据配置中"
      subTitle="此工段的数据源尚未配置，请先对接飞书电子表格"
    />
  )
}

