/**
 * 厂区矢量底图生成器（2.5D 等轴测）。
 *
 * 数据来源：BM.EP.101-05 厂区平面图（2023.11.12），建筑中心点沿用
 * campus_buildings 种子的标定结果，footprint（w×d）与高度按图纸目测比例
 * 做风格化还原——这是示意底图，非测绘图。
 *
 * 用法：node scripts/generate-campus-map.mjs
 * 输出：
 *   - public/safety/campus-map.svg          底图（含建筑/道路/围墙/名称）
 *   - stdout 打印建筑名 → 标记坐标(JSON)，用于回写 campus_buildings
 */
/* eslint-disable no-console -- 构建脚本需在 stdout 输出坐标供管道消费 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

// ── 平面坐标：与 campus_buildings 同一套百分比坐标（0-100） ──
// 条目：[名称, 类别, cx, cy, w, d, 高度(单位), 变体]
// 类别: workshop/warehouse/utility/env/tank/office/logistics/sports/water
// 变体: cylinders=立式储罐组, water=水面, flat=球场
const BUILDINGS = [
  // 办公后勤（南）
  ['办公质检楼', 'office', 55, 87, 12, 6, 4.6],
  ['食堂', 'office', 74, 84.8, 6.5, 4, 2.6],
  ['倒班楼西楼', 'office', 82.5, 85, 6.6, 3.8, 4.6],
  ['倒班楼东楼', 'office', 92, 85, 6.4, 3.8, 4.6],
  ['门卫', 'logistics', 66, 79.7, 2, 1.2, 1.2],
  ['物流门房', 'logistics', 2.2, 96.5, 2, 1.2, 1.2],
  // 体育设施（西南）
  ['足球场', 'sports', 8.5, 89, 9, 6, 0],
  ['篮球场', 'sports', 19.3, 84.4, 5, 3, 0],
  ['网球场', 'sports', 17.6, 90.4, 4.5, 3, 0],
  // 西侧库房区
  ['315仓库', 'warehouse', 10, 48.5, 9.5, 3.5, 2.8],
  ['313仓库', 'warehouse', 10, 58.4, 9.5, 3.6, 2.8],
  ['液体原料库', 'warehouse', 10.3, 67.2, 9.5, 3.5, 2.8],
  ['311仓库', 'warehouse', 10, 74.9, 9.5, 3.6, 2.8],
  // 西侧公用工程（北）
  ['液氨压缩机房', 'utility', 9, 7, 4, 2.5, 2],
  ['液氨储区', 'tank', 8.5, 10.5, 3.4, 2.4, 2.4, 'cylinders'],
  // 中部公用工程（西）
  ['锅炉房（516）', 'utility', 33.4, 27, 4.2, 5.4, 3.8],
  ['烟囱', 'utility', 39.3, 27.4, 1.4, 1.4, 8, 'cylinders'],
  ['煤仓（515）', 'utility', 46.4, 30.5, 4.4, 13, 4.5],
  ['除盐水站（518）', 'utility', 34.1, 34.6, 7, 3.4, 2.4],
  ['203车间', 'workshop', 34, 40.3, 10.5, 4, 3.4],
  ['供水站（512）', 'utility', 43, 48, 5, 3, 1.8],
  ['动力中心（513）', 'utility', 22, 48, 7, 3.5, 2.8],
  // 中部车间/库房带（101/102 为一栋建筑内分设两个车间：东侧一车间、西侧二车间）
  ['201一车间', 'workshop', 86, 31.5, 19, 4, 3.4],
  ['201二车间', 'workshop', 86, 24.2, 19, 4, 3.4],
  ['101车间', 'workshop', 79, 67.2, 14, 4.4, 3.4, 'split', ['101一车间', '101二车间']],
  ['102车间', 'workshop', 79, 75.5, 14, 4.4, 3.4, 'split', ['102一车间', '102二车间']],
  ['203车间（北）', 'workshop', 26, 58.4, 16, 3.6, 3.2],
  ['203车间（南）', 'workshop', 26, 66.4, 16, 4.2, 3.2],
  ['103车间', 'workshop', 26, 75.5, 16, 4, 3.4],
  ['循环水池', 'water', 50, 54.7, 23, 1.8, 0.3, 'water'],
  ['循环水站（511）', 'utility', 43.5, 58.4, 9.4, 3.8, 2.2],
  ['循环水站（502）', 'utility', 58, 58.5, 8.8, 3.9, 2.2],
  ['动力中心（501）', 'utility', 78, 58.5, 13.5, 4, 2.8],
  // 东部仓库列
  ['303仓库', 'warehouse', 92, 58.5, 6.3, 4.2, 2.8],
  ['302仓库', 'warehouse', 92, 67.2, 6.3, 4.2, 2.8],
  ['301仓库', 'warehouse', 92, 75.6, 6.3, 4.2, 2.8],
  // 中部公用工程（东）
  ['破碎间', 'utility', 54.9, 24.1, 3.4, 3, 1.8],
  ['RTO', 'env', 60.2, 24.2, 4, 2.6, 2.4],
  ['锅炉房（506）', 'utility', 65, 25.5, 4.4, 2.8, 3.8],
  ['煤仓（504）', 'utility', 55.5, 32.8, 2.8, 8.6, 4.2],
  ['202车间', 'workshop', 65, 35, 14, 7.2, 3.4],
  ['除盐水站（501）', 'utility', 55, 38.7, 4.2, 2.4, 2.2],
  ['配电室', 'utility', 61.5, 40, 2.6, 2.6, 1.6],
  ['供水站（503）', 'utility', 58, 48, 9.5, 2.5, 1.8],
  // 污水处理区（北）：两座污水处理系统
  ['污水处理系统（一）', 'env', 41.5, 12, 12.4, 10, 1.6],
  ['污水处理系统（二）', 'env', 54.5, 12, 12.4, 10, 1.6],
  ['曝气池', 'water', 34, 8, 7, 5, 0.3, 'water'],
  ['二沉池', 'tank', 43, 8.5, 3.2, 3.2, 1.8, 'cylinders'],
  ['污泥浓缩池', 'tank', 33, 15, 2.8, 2.8, 1.6, 'cylinders'],
  // 东北生产区
  ['MVR', 'utility', 82.4, 10.5, 3.6, 4, 3.8],
  ['过滤生产区', 'workshop', 90, 9.6, 10, 2.2, 2.8],
  ['干燥间', 'workshop', 90, 12.8, 10, 3.6, 2.8],
  ['机修间', 'utility', 93.2, 7.4, 2.2, 1.6, 1.8],
  // 东南罐区/危险品库
  ['甲类罐区', 'tank', 80.5, 39, 7, 2.6, 2.2, 'cylinders'],
  ['装卸罐', 'tank', 80.5, 41.8, 2.4, 1.6, 1.4],
  ['泵房（305）', 'utility', 78, 42.6, 2.4, 1.4, 1.4],
  ['危险品库', 'warehouse', 91.5, 39.7, 6.8, 3.6, 2.6],
]

// 道路：E-W 横路 [y, x起, x终]，N-S 竖路 [x, y起, y终]（单位 %，路宽约 1.8）
const ROADS_EW = [
  [26, 3, 97],
  [45.3, 3, 97],
  [52.6, 3, 97],
  [61.9, 3, 97],
  [70.2, 3, 97],
  [78.8, 3, 97],
  [93.2, 3, 97],
]
const ROADS_NS = [
  [17.3, 1.5, 96.5],
  [36.5, 24, 96.5],
  [47.6, 24, 96.5],
  [63.6, 24, 93],
  [71.4, 44, 93],
  [87.2, 16, 96.5],
  [97.2, 1.5, 96.5],
]
const ROAD_W = 1.9

// 围墙：矩形边界（%），南面主入口开口 x 56-64，东面开口 y 44-48
const WALL = { x0: 1.2, y0: 0.8, x1: 98.8, y1: 97.6, h: 0.9 }

// ── 投影与画布 ──
const K = 5.6 // px / 单位
const OX = 600
const OY = 40
const CANVAS_W = 1200
const CANVAS_H = 645
const project = (x, y, z = 0) => ({
  x: OX + (x - y) * 0.866 * K,
  y: OY + (x + y) * 0.5 * K - z * K,
})

const PALETTE = {
  workshop: { top: '#c9d9f2', left: '#a9c0e6', right: '#b7cdee', edge: '#6f8fbd', label: '#1f3a5f' },
  warehouse: { top: '#f0e2c0', left: '#e2cd9c', right: '#ead6ab', edge: '#b3945f', label: '#5f4a1f' },
  utility: { top: '#cfe8e4', left: '#b3d8d2', right: '#c2e0db', edge: '#6ba39a', label: '#1f4f47' },
  env: { top: '#cfe6cf', left: '#b4d6b4', right: '#c4dfc4', edge: '#74a874', label: '#235c23' },
  tank: { top: '#f8d8c0', left: '#efc2a2', right: '#f4cdae', edge: '#c68a5c', label: '#6b3f1c' },
  office: { top: '#dcd4f2', left: '#c6b9e8', right: '#d2c7ee', edge: '#8b7abf', label: '#3a2d6b' },
  logistics: { top: '#e2e2e2', left: '#d2d2d2', right: '#dadada', edge: '#9a9a9a', label: '#444444' },
  sports: { top: '#c8e6c4', left: '#c8e6c4', right: '#c8e6c4', edge: '#8fbb8a', label: '#2f5c2a' },
  water: { top: '#b5d8f2', left: '#b5d8f2', right: '#b5d8f2', edge: '#7fb3dd', label: '#1f4f7a' },
}
const ROAD_COLOR = '#dbd9d3'
const GROUND_COLOR = '#eef0e7'
const WALL_COLOR = '#b8b6b0'

const fmt = (n) => Math.round(n * 10) / 10

function boxFaces(cx, cy, w, d, h) {
  const hx = w / 2
  const hy = d / 2
  const corners = [
    [cx - hx, cy - hy],
    [cx + hx, cy - hy],
    [cx + hx, cy + hy],
    [cx - hx, cy + hy],
  ].map(([x, y]) => project(x, y, 0))
  const top = corners.map((p) => ({ x: p.x, y: p.y - h * K }))
  // 观察方向：屏幕上 (x+y) 越大越靠前 → 朝左下与朝右下的两个面可见
  return { corners, top }
}

function poly(points) {
  return points.map((p) => `${fmt(p.x)},${fmt(p.y)}`).join(' ')
}

function buildingSvg(entry) {
  const [name, cat, cx, cy, w, d, h, variant, displayLabel] = entry
  const pal = PALETTE[cat] || PALETTE.utility
  const parts = []
  if (variant === 'cylinders') {
    // 立式罐组/烟囱/池：沿主轴均布圆柱
    const horizontal = w >= d
    const count = name === '曝气池' ? 2 : Math.max(1, Math.round((horizontal ? w : d) / 3))
    const r = (horizontal ? d : w) / 2
    const span = (horizontal ? w : d) - r * 2
    for (let i = 0; i < count; i++) {
      const t = count === 1 ? 0.5 : i / (count - 1)
      const ox = horizontal ? cx - w / 2 + r + span * t : cx
      const oy = horizontal ? cy : cy - d / 2 + r + span * t
      parts.push(cylinderSvg(ox, oy, r, h, pal))
    }
    parts.push(labelSvg(name, ...Object.values(project(cx, cy, h + 1.2)), pal.label))
    return parts.join('\n')
  }
  if (variant === 'water') {
    const { corners, top } = boxFaces(cx, cy, w, d, h)
    parts.push(`<polygon points="${poly(corners)}" fill="${pal.top}" stroke="${pal.edge}" stroke-width="0.8"/>`)
    parts.push(`<polygon points="${poly(top)}" fill="#b5d8f2" stroke="#7fb3dd" stroke-width="0.8"/>`)
    parts.push(labelSvg(name, ...Object.values(project(cx, cy, h + 1)), pal.label))
    return parts.join('\n')
  }
  const { corners, top } = boxFaces(cx, cy, w, d, h)
  const [, c1, c2, c3] = corners
  const [, t1, t2, t3] = top
  // 两个可见侧面：前左（c3-c2）与前右（c2-c1）
  parts.push(`<polygon points="${poly([c3, c2, t2, t3])}" fill="${pal.left}" stroke="${pal.edge}" stroke-width="0.6"/>`)
  parts.push(`<polygon points="${poly([c2, c1, t1, t2])}" fill="${pal.right}" stroke="${pal.edge}" stroke-width="0.6"/>`)
  parts.push(`<polygon points="${poly(top)}" fill="${pal.top}" stroke="${pal.edge}" stroke-width="0.6"/>`)
  if (variant === 'split') {
    // 一栋建筑内分设两个车间：屋顶画分隔线，两个半区各标注车间名
    // splitLabels = [东侧车间名, 西侧车间名]
    const d1 = project(cx, cy - d / 2, h)
    const d2 = project(cx, cy + d / 2, h)
    parts.push(`<line x1="${fmt(d1.x)}" y1="${fmt(d1.y)}" x2="${fmt(d2.x)}" y2="${fmt(d2.y)}" stroke="${pal.edge}" stroke-width="1" stroke-dasharray="4 3"/>`)
    const [eastName, westName] = displayLabel || ['', '']
    const eastAt = project(cx + w / 4, cy, h + 1)
    const westAt = project(cx - w / 4, cy, h + 1)
    parts.push(labelSvg(eastName, eastAt.x, eastAt.y, pal.label, 10))
    parts.push(labelSvg(westName, westAt.x, westAt.y, pal.label, 10))
    return parts.join('\n')
  }
  const labelAt = project(cx, cy, h + 1)
  parts.push(labelSvg(name, labelAt.x, labelAt.y, pal.label))
  return parts.join('\n')
}

function cylinderSvg(cx, cy, r, h, pal) {
  const base = project(cx, cy, 0)
  const top = project(cx, cy, h)
  const rw = r * 0.866 * K * 2
  const rh = r * 0.5 * K
  return `<g>` +
    `<path d="M${fmt(base.x - rw / 2)},${fmt(base.y)} L${fmt(base.x - rw / 2)},${fmt(top.y)} A${fmt(rw / 2)},${fmt(rh)} 0 0 1 ${fmt(base.x + rw / 2)},${fmt(top.y)} L${fmt(base.x + rw / 2)},${fmt(base.y)} Z" fill="${pal.left}" stroke="${pal.edge}" stroke-width="0.6"/>` +
    `<ellipse cx="${fmt(top.x)}" cy="${fmt(top.y)}" rx="${fmt(rw / 2)}" ry="${fmt(rh)}" fill="${pal.top}" stroke="${pal.edge}" stroke-width="0.6"/>` +
    `</g>`
}

function labelSvg(text, x, y, color, size = 11) {
  return `<text x="${fmt(x)}" y="${fmt(y)}" font-size="${size}" font-weight="600" fill="${color}" ` +
    `text-anchor="middle" stroke="#ffffff" stroke-width="2.4" paint-order="stroke" font-family="system-ui, 'Microsoft YaHei', sans-serif">${text}</text>`
}

// ── 组装 ──
const svg = []

// 地面
const ground = [
  project(WALL.x0, WALL.y0),
  project(WALL.x1, WALL.y0),
  project(WALL.x1, WALL.y1),
  project(WALL.x0, WALL.y1),
].map((p) => `${fmt(p.x)},${fmt(p.y)}`).join(' ')
svg.push(`<polygon points="${ground}" fill="${GROUND_COLOR}" stroke="none"/>`)

// 道路（先横后竖，压在地面之上）
function roadBand(x0, y0, x1, y1) {
  const pts = [
    project(x0 - ROAD_W / 2, y0 - ROAD_W / 2),
    project(x1 + ROAD_W / 2, y0 - ROAD_W / 2),
    project(x1 + ROAD_W / 2, y1 + ROAD_W / 2),
    project(x0 - ROAD_W / 2, y1 + ROAD_W / 2),
  ].map((p) => `${fmt(p.x)},${fmt(p.y)}`).join(' ')
  svg.push(`<polygon points="${pts}" fill="${ROAD_COLOR}" opacity="0.9"/>`)
}
for (const [y, x0, x1] of ROADS_EW) roadBand(x0, y, x1, y)
for (const [x, y0, y1] of ROADS_NS) roadBand(x, y0, x, y1)

// 围墙（四段，南面主入口 x56-64 留口，东面 y44-48 留口）
const wallSegments = [
  [WALL.x0, WALL.y0, WALL.x1, WALL.y0],
  [WALL.x1, WALL.y0, WALL.x1, 44],
  [WALL.x1, 48, WALL.x1, WALL.y1],
  [WALL.x1, WALL.y1, 64, WALL.y1],
  [56, WALL.y1, WALL.x0, WALL.y1],
  [WALL.x0, WALL.y1, WALL.x0, WALL.y0],
]
for (const [x0, y0, x1, y1] of wallSegments) {
  const a = project(x0, y0, 0)
  const b = project(x1, y1, 0)
  const a2 = project(x0, y0, WALL.h)
  const b2 = project(x1, y1, WALL.h)
  svg.push(`<polygon points="${fmt(a.x)},${fmt(a.y)} ${fmt(b.x)},${fmt(b.y)} ${fmt(b2.x)},${fmt(b2.y)} ${fmt(a2.x)},${fmt(a2.y)}" fill="${WALL_COLOR}" stroke="#8f8d86" stroke-width="0.5"/>`)
}

// 建筑按深度排序（远→近：x+y 小的先画）
const sorted = [...BUILDINGS].sort((a, b) => a[2] + a[3] - (b[2] + b[3]))
for (const b of sorted) svg.push(buildingSvg(b))

// 指北针
const nBase = project(96, 6, 0)
svg.push(`<g><line x1="${fmt(nBase.x)}" y1="${fmt(nBase.y)}" x2="${fmt(nBase.x)}" y2="${fmt(nBase.y - 34)}" stroke="#5d5b54" stroke-width="2"/>` +
  `<polygon points="${fmt(nBase.x)},${fmt(nBase.y - 40)} ${fmt(nBase.x - 5)},${fmt(nBase.y - 28)} ${fmt(nBase.x + 5)},${fmt(nBase.y - 28)}" fill="#5d5b54"/>` +
  `<text x="${fmt(nBase.x)}" y="${fmt(nBase.y + 12)}" font-size="12" font-weight="700" fill="#5d5b54" text-anchor="middle">N</text></g>`)

const out = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${CANVAS_W} ${CANVAS_H}" font-family="system-ui, 'Microsoft YaHei', sans-serif">\n` +
  `<rect width="${CANVAS_W}" height="${CANVAS_H}" fill="#f7f6f2"/>\n` +
  svg.join('\n') + '\n</svg>\n'

const outPath = join(root, 'public', 'safety', 'campus-map.svg')
mkdirSync(dirname(outPath), { recursive: true })
writeFileSync(outPath, out, 'utf8')

// 输出标记坐标（建筑地面中心投影 → 画布百分比）
const markerCoords = {}
for (const [name, , cx, cy] of BUILDINGS) {
  const p = project(cx, cy, 0)
  markerCoords[name] = {
    x_pct: fmt((p.x / CANVAS_W) * 100),
    y_pct: fmt((p.y / CANVAS_H) * 100),
  }
}
console.log(JSON.stringify(markerCoords, null, 2))
console.error(`written: ${outPath}`)
