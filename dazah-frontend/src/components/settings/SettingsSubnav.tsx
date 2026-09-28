import type { ReactNode } from 'react'

export interface SettingsSubnavItem {
  key: string
  label: string
  icon: ReactNode
  children: ReactNode
}

interface SettingsSubnavProps {
  ariaLabel: string
  items: SettingsSubnavItem[]
  activeKey: string
  onChange: (key: string) => void
  showNav?: boolean
}

export default function SettingsSubnav({ ariaLabel, items, activeKey, onChange, showNav = true }: SettingsSubnavProps) {
  const selected = items.find((item) => item.key === activeKey) ?? items[0]
  if (!selected) return null

  return (
    <div className="min-w-0 overflow-hidden rounded-[var(--rounded-xl)] border border-[var(--color-hairline-soft)] bg-[var(--color-canvas)] shadow-sm lg:flex">
      {showNav && (
        <nav aria-label={ariaLabel} className="shrink-0 border-b border-[var(--color-hairline-soft)] p-2 lg:w-56 lg:border-b-0 lg:border-r lg:p-3">
          <div className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-x-visible">
            {items.map((item) => (
              <button
                key={item.key}
                type="button"
                aria-current={selected.key === item.key ? 'page' : undefined}
                onClick={() => onChange(item.key)}
                className={`flex min-h-10 shrink-0 items-center gap-3 rounded-[var(--rounded-md)] px-3 py-2 text-left text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] lg:w-full ${selected.key === item.key
                  ? 'bg-[rgba(86,69,212,0.09)] text-[var(--color-primary)] shadow-[inset_3px_0_var(--color-primary)]'
                  : 'text-[var(--color-slate)] hover:bg-[var(--color-surface-soft)] hover:text-[var(--color-ink)]'}`}
              >
                <span aria-hidden="true" className="inline-flex shrink-0 text-base">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        </nav>
      )}
      <div className="min-w-0 flex-1 p-4 sm:p-5" key={selected.key}>
        {selected.children}
      </div>
    </div>
  )
}
