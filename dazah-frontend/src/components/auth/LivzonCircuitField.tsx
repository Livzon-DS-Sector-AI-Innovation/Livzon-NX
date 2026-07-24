import styles from './IdentityBubble.module.css'

function coordinate(value: number) {
  return Math.round(value * 100) / 100
}

const contourScales = Array.from({ length: 18 }, (_, index) => ({
  id: index,
  scale: (1 - index * 0.017).toFixed(3),
  opacity: coordinate(0.46 - index * 0.009),
}))

const signalBands = Array.from({ length: 9 }, (_, index) => {
  const y = 325 + (index - 4) * 12
  const step = ((index % 3) - 1) * 7

  return {
    id: index,
    left: `M458 ${y}H526L542 ${y + step}H590L606 ${y}H690`,
    right: `M1142 ${y}H1074L1058 ${y + step}H1010L994 ${y}H910`,
    leftNodeX: 474 + (index % 4) * 42,
    rightNodeX: 1126 - (index % 4) * 42,
    y,
  }
})

const radialTraces = Array.from({ length: 22 }, (_, index) => {
  const angle = (index / 22) * Math.PI * 2
  const innerRadius = 112
  const elbowRadius = 212 + (index % 4) * 24
  const outerRadius = 292 + (index % 6) * 24
  const point = (radius: number, verticalScale: number) =>
    `${coordinate(800 + Math.cos(angle) * radius)},${coordinate(
      325 + Math.sin(angle) * radius * verticalScale,
    )}`

  const node = point(outerRadius, 0.68).split(',')

  return {
    id: index,
    points: `${point(innerRadius, 0.68)} ${point(elbowRadius, 0.68)} ${point(
      outerRadius,
      0.68,
    )}`,
    nodeX: node[0],
    nodeY: node[1],
  }
})

export function LivzonCircuitField() {
  return (
    <div className={styles.circuitField} aria-hidden="true">
      <div className={`${styles.telemetry} ${styles.telemetryLeft}`}>
        <strong>AUDIT COORDINATES</strong>
        <span>X 8721.44　Y 4395.21　Z 104.32</span>
      </div>
      <div className={`${styles.telemetry} ${styles.telemetryRight}`}>
        <strong>SYS-ID　D2-7A-HQ-INT</strong>
        <span>NODE　04　SECTOR　B-17</span>
      </div>

      <svg
        className={styles.circuitSvg}
        viewBox="0 0 1600 650"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <linearGradient id="livzon-scan" x1="0" x2="1">
            <stop offset="0" stopColor="#62ecff" stopOpacity="0" />
            <stop offset="0.5" stopColor="#62ecff" stopOpacity="0.86" />
            <stop offset="1" stopColor="#62ecff" stopOpacity="0" />
          </linearGradient>
          <filter id="livzon-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <mask id="livzon-center-cut">
            <rect width="1600" height="650" fill="white" />
            <ellipse cx="800" cy="325" rx="168" ry="94" fill="black" />
          </mask>
        </defs>

        <g className={styles.circuitWord} mask="url(#livzon-center-cut)">
          {contourScales.map((contour) => (
            <text
              key={contour.id}
              x="800"
              y="520"
              textAnchor="middle"
              textLength="1512"
              lengthAdjust="spacingAndGlyphs"
              className={styles.circuitWordContour}
              opacity={contour.opacity}
              transform={`translate(800 325) scale(${contour.scale}) translate(-800 -325)`}
            >
              LIVZON
            </text>
          ))}
        </g>

        <g className={styles.signalBands}>
          {signalBands.map((band) => (
            <g key={band.id}>
              <path d={band.left} />
              <path d={band.right} />
              <circle cx={band.leftNodeX} cy={band.y} r="1.8" />
              <circle cx={band.rightNodeX} cy={band.y} r="1.8" />
            </g>
          ))}
        </g>

        <g className={styles.radialTraces}>
          {radialTraces.map((trace) => (
            <g key={trace.id}>
              <polyline points={trace.points} />
              <circle cx={trace.nodeX} cy={trace.nodeY} r="1.8" />
            </g>
          ))}
        </g>

        <g className={styles.fieldBrackets}>
          <path d="M688 260v-17h20M912 260v-17h-20M688 390v17h20M912 390v17h-20" />
        </g>

        <rect
          x="-380"
          y="320"
          width="620"
          height="4"
          fill="url(#livzon-scan)"
          className={styles.circuitScanner}
          filter="url(#livzon-glow)"
        />
        <rect
          x="1360"
          y="326"
          width="620"
          height="4"
          fill="url(#livzon-scan)"
          className={`${styles.circuitScanner} ${styles.circuitScannerReverse}`}
          filter="url(#livzon-glow)"
        />
      </svg>

      <span className={`${styles.edgeCross} ${styles.edgeCrossLeft}`}>+</span>
      <span className={`${styles.edgeCross} ${styles.edgeCrossRight}`}>+</span>
      <span className={`${styles.edgeCorner} ${styles.edgeCornerTopLeft}`} />
      <span className={`${styles.edgeCorner} ${styles.edgeCornerTopRight}`} />
      <span className={`${styles.edgeCorner} ${styles.edgeCornerBottomLeft}`} />
      <span className={`${styles.edgeCorner} ${styles.edgeCornerBottomRight}`} />
      <span className={styles.topRuler} />
      <span className={styles.bottomRuler} />
    </div>
  )
}
