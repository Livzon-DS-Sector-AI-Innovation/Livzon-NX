"use client"

import type { ReactNode } from 'react'
import Link from 'next/link'
import { Card, Col, Row } from 'antd'

export interface ModuleLandingEntry {
  title: string
  description: string
  href: string
  icon: ReactNode
  dashboard?: boolean
}

interface ModuleLandingCardsProps {
  title: string
  description: string
  entries: ModuleLandingEntry[]
}

export function ModuleLandingCards({ title, description, entries }: ModuleLandingCardsProps) {
  return (
    <section aria-label={`${title}功能入口`}>
      <header className="mb-6">
        <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">{title}</h1>
        <p className="text-[14px] text-[var(--color-steel)]">{description}</p>
      </header>
      <Row gutter={[16, 16]}>
        {entries.map((entry) => (
          <Col xs={24} sm={12} lg={8} key={entry.href}>
            <Link href={entry.href} className="block h-full rounded-[var(--rounded-sm)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]">
              <Card hoverable className="h-full">
                <div className="flex items-start gap-3">
                  <span aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--rounded-sm)] bg-[var(--color-surface)] text-[20px] text-[var(--color-primary)]">
                    {entry.icon}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)]">{entry.title}</h2>
                      {entry.dashboard && <span className="rounded-[var(--rounded-sm)] bg-[var(--color-surface)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--color-primary)]">仪表盘</span>}
                    </div>
                    <p className="mt-1 text-[13px] leading-5 text-[var(--color-steel)]">{entry.description}</p>
                  </div>
                </div>
              </Card>
            </Link>
          </Col>
        ))}
      </Row>
    </section>
  )
}
