export default function HrLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <ViewportOverlays>{children}</ViewportOverlays>
}
import ViewportOverlays from '@/components/shared/ViewportOverlays'
