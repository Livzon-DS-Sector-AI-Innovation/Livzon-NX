export default function DashboardLoading() {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <div className="space-y-2">
          <div className="h-7 w-44 animate-pulse rounded-[var(--rounded-sm)] bg-[var(--color-hairline)]" />
          <div className="h-4 w-72 animate-pulse rounded-[var(--rounded-sm)] bg-[var(--color-hairline-soft)]" />
        </div>
        <div className="h-9 w-28 animate-pulse rounded-[var(--rounded-md)] bg-[var(--color-hairline)]" />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {Array.from({ length: 3 }, (_, index) => (
          <div
            key={index}
            className="h-24 animate-pulse rounded-[var(--rounded-lg)] border border-[var(--color-hairline)] bg-[var(--color-canvas)]"
          />
        ))}
      </div>

      <div className="space-y-3 rounded-[var(--rounded-lg)] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4">
        <div className="h-5 w-36 animate-pulse rounded-[var(--rounded-sm)] bg-[var(--color-hairline)]" />
        <div className="space-y-2">
          {Array.from({ length: 8 }, (_, index) => (
            <div
              key={index}
              className="h-9 animate-pulse rounded-[var(--rounded-sm)] bg-[var(--color-surface)]"
            />
          ))}
        </div>
      </div>
    </div>
  )
}
