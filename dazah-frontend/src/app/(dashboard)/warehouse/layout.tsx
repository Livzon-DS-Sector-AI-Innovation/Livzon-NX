import { WarehouseQueryProvider } from '@/components/warehouse'

export default function WarehouseLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <WarehouseQueryProvider>{children}</WarehouseQueryProvider>
}
