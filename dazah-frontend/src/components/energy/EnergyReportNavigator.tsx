import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Empty, Input, Skeleton } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { reportQuery, type WorkbookDataset } from '@/lib/api/energy-ledger'
import styles from './EnergyWorkbookGrid.module.css'

const GROUPS = ['汇总报表', '计量读数', '用量明细', '车间报表']
function group(dataset: WorkbookDataset) {
  if (dataset.name === '日总量') return '汇总报表'
  if (dataset.name.endsWith('车间')) return '车间报表'
  return dataset.kind === 'reading' || dataset.kind === 'mixed' ? '计量读数' : '用量明细'
}

export function EnergyReportNavigator({ datasets, selected, year, month, loading, onSelect }: {
  datasets: WorkbookDataset[]; selected: string; year: number; month: number; loading: boolean; onSelect: (name: string) => void
}) {
  const [search, setSearch] = useState('')
  const navigation = useRef<HTMLElement>(null)
  useEffect(() => {
    const container = navigation.current
    const active = container?.querySelector<HTMLElement>('[aria-current="page"]')
    if (!container || !active) return
    const reveal = () => {
      const bounds = container.getBoundingClientRect(), link = active.getBoundingClientRect()
      if (link.top < bounds.top) container.scrollTop += link.top - bounds.top
      else if (link.bottom > bounds.bottom) container.scrollTop += link.bottom - bounds.bottom
    }
    reveal()
    const observer = new ResizeObserver(reveal)
    observer.observe(container)
    return () => observer.disconnect()
  }, [selected, datasets, search])
  const filtered = datasets.filter(item => item.name.toLowerCase().includes(search.trim().toLowerCase()))
  return <aside className={styles.reportDirectory}>
    <div className={styles.directoryHeading}><strong>报表目录</strong><span>{datasets.length} 张</span></div>
    <Input aria-label="搜索报表" prefix={<SearchOutlined />} placeholder="搜索报表名称" value={search} allowClear onChange={event => setSearch(event.target.value)} />
    {loading ? <Skeleton active paragraph={{ rows: 6 }} /> : <nav ref={navigation} aria-label="报表工作表" className={styles.reportNavigation}>
      {GROUPS.map(label => {
        const items = filtered.filter(item => group(item) === label)
        return items.length > 0 && <section key={label} aria-label={label}>
          <h4>{label}<span>{items.length}</span></h4>
          {items.map(item => <Link key={item.name} prefetch={false} className={styles.reportLink} href={`/energy/reports?${reportQuery({ year, month, dataset: item.name })}`} aria-current={item.name === selected ? 'page' : undefined} onClick={event => {
            if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
            event.preventDefault()
            onSelect(item.name)
          }}>{item.name}</Link>)}
        </section>
      })}
      {!filtered.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={datasets.length ? '没有匹配的报表' : '暂无可查询报表'} />}
    </nav>}
  </aside>
}
