import ViewportOverlays from '@/components/shared/ViewportOverlays'

export default function QualityLayout({ children }: { children: React.ReactNode }) {
  return <ViewportOverlays>{children}</ViewportOverlays>
}
