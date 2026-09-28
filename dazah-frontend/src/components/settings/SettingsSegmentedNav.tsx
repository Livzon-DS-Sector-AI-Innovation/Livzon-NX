import type { KeyboardEvent } from 'react'

interface SettingsSegmentedItem {
  key: string
  label: string
}

interface SettingsSegmentedNavProps {
  ariaLabel: string
  items: readonly SettingsSegmentedItem[]
  activeKey: string
  onChange: (key: string) => void
  panelId: string
}

export default function SettingsSegmentedNav({ ariaLabel, items, activeKey, onChange, panelId }: SettingsSegmentedNavProps) {
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const nextIndex = event.key === 'ArrowRight' ? (index + 1) % items.length
      : event.key === 'ArrowLeft' ? (index - 1 + items.length) % items.length
        : event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : -1
    if (nextIndex < 0) return
    event.preventDefault()
    onChange(items[nextIndex].key)
    event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[nextIndex]?.focus()
  }

  return (
    <div role="tablist" aria-label={ariaLabel} className="flex w-fit max-w-full gap-1 overflow-x-auto rounded-full bg-[var(--color-surface)] p-1">
      {items.map((item, index) => (
        <button
          key={item.key}
          id={`${panelId}-tab-${item.key}`}
          type="button"
          role="tab"
          aria-selected={activeKey === item.key}
          aria-controls={panelId}
          tabIndex={activeKey === item.key ? 0 : -1}
          onClick={() => onChange(item.key)}
          onKeyDown={(event) => onKeyDown(event, index)}
          className={`inline-flex shrink-0 items-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] ${activeKey === item.key
            ? 'bg-[var(--color-canvas)] text-[var(--color-ink-deep)] shadow-sm'
            : 'text-[var(--color-slate)] hover:bg-[var(--color-canvas)] hover:text-[var(--color-ink)]'}`}
        >
          <span aria-hidden="true" className={`size-1.5 rounded-full ${activeKey === item.key ? 'bg-[var(--color-primary)]' : 'bg-transparent'}`} />
          {item.label}
        </button>
      ))}
    </div>
  )
}
