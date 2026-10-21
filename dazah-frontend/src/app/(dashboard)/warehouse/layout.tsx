import { WarehouseQueryProvider } from '@/components/warehouse'
import ViewportOverlays from '@/components/shared/ViewportOverlays'

export default function WarehouseLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <ViewportOverlays><WarehouseQueryProvider>{children}</WarehouseQueryProvider></ViewportOverlays>
}
