# UI 设计指南

> **设计类型**: App 设计（应用架构设计）
> **确认检查**: 本指南适用于可交互的应用/网站/工具。

> ℹ️ Section 1 为设计意图与决策上下文。Code agent 实现时以 Section 2 及之后的具体参数为准。

## 1. Design Archetype (设计原型)

### 1.1 内容理解（每项一句话，不展开）

- **目标用户**: 制药车间巡检员（移动端高频录入）与管理员（PC端审核管理），需零思考操作路径
- **核心目的**: 引导行动（30秒极速录入）+ 建立信任（GMP合规数据管控）
- **情绪基调**: 洁净专注 / 避免焦虑混乱与视觉疲劳

### 1.2 设计方向（每项一行）

- **Design Style**: Soft Blocks 柔色块 — 医疗洁净风需柔和层次+轻圆角投影，兼顾工业严谨与触屏亲和
- **Application Type**: Admin/SaaS + Mobile Tool — 多角色后台管理系统，含移动端录入工具页
- **Aesthetic Direction**: 白色基底+医疗蓝主调，卡片微投影营造洁净悬浮感，状态色克制精准

## 2. Color System (色彩系统)

**色彩关系**: 医疗蓝主色 + 极浅蓝灰底 + 深墨文字 + 三态语义色点缀
**配色设计理由**: GMP洁净车间气质要求低视觉噪音，蓝色传递专业信任，浅灰底减少长时间使用疲劳
**主色推导**: primary 取医疗蓝(HSL 210°)关联"合规记录"核心行动，仅用于主按钮/激活态/关键CTA
**使用比例**: 60% 白/浅灰中性底 / 30% 卡片白+边框 / 10% 医疗蓝primary；语义色仅状态标签/数字高亮

### 2.1 主题颜色

| Token                | HSL 值             | 说明                                     |
| -------------------- | ------------------ | ---------------------------------------- |
| `background`         | hsl(210 20% 97%)   | 极浅蓝灰页面底色，营造洁净基调           |
| `card`               | hsl(0 0% 100%)     | 纯白卡片容器                             |
| `foreground`         | hsl(215 25% 18%)   | 深墨主文字，高可读性                     |
| `muted-foreground`   | hsl(215 15% 50%)   | 次要说明文字                             |
| `primary`            | hsl(210 85% 48%)   | 医疗蓝主交互色                           |
| `primary-foreground` | hsl(0 0% 100%)     | 主按钮白色文字                           |
| `accent`             | hsl(210 25% 94%)   | 次级交互反馈（hover/focus/骨架屏）       |
| `accent-foreground`  | hsl(215 25% 25%)   | accent 上的深色文字                      |
| `border`             | hsl(210 15% 90%)   | 轻量边框                                 |

### 2.2 Sidebar 颜色（仅PC端）

| Token                        | HSL 值             | 说明                           |
| ---------------------------- | ------------------ | ------------------------------ |
| `sidebar`                    | hsl(210 20% 98%)   | 导航区浅底，与内容区微区分     |
| `sidebar-foreground`         | hsl(215 20% 35%)   | 导航默认文字                   |
| `sidebar-primary`            | hsl(210 85% 48%)   | 激活项背景=主色                |
| `sidebar-primary-foreground` | hsl(0 0% 100%)     | 激活项白色文字                 |
| `sidebar-accent`             | hsl(210 25% 94%)   | Hover 态背景                   |
| `sidebar-accent-foreground`  | hsl(215 25% 25%)   | Hover 态文字                   |
| `sidebar-border`             | hsl(210 15% 92%)   | 右侧分隔线                     |
| `sidebar-ring`               | hsl(210 85% 48%)   | 聚焦环                         |

### 2.3 Topbar/Header 设计策略（仅移动端）

- **背景策略**: `bg-card` + 底部 `border-border`，保持洁净感
- **文字/图标**: 默认 `text-foreground`，返回箭头与标题同色
- **边框与分隔**: 底部 `border-border` 细线，无阴影

### 2.4 语义颜色

| 用途       | HSL 值              | 衍生说明                              |
| ---------- | ------------------- | ------------------------------------- |
| 成功/已审核 | hsl(152 60% 42%)    | 绿色系，边框中饱和，背景 hsl(152 55% 95%) |
| 警告/待审核 | hsl(32 85% 50%)     | 橙色系，数字高亮用此色，背景 hsl(32 80% 95%) |
| 错误/已驳回 | hsl(4 75% 52%)      | 红色系，边框中饱和，背景 hsl(4 70% 96%) |

## 3. Typography (字体排版)

- **Heading**: Inter, "PingFang SC", "Microsoft YaHei", sans-serif
- **Body**: Inter, "PingFang SC", "Microsoft YaHei", sans-serif
- **字体策略**: Inter 提供清晰数据可读性，中文回退栈确保跨平台一致；标题 font-bold，正文 font-normal，数字 tabular-nums 对齐

## 4. Layout Strategy (布局策略)

- **导航策略**: PC端 Sidebar（持久导航+权限控制）；移动端顶部 Topbar + 底部快捷入口卡片（替代侧边栏）
- **页面架构**: PC端 Sidebar + 右侧内容区 max-w-[1400px]；移动端全宽单列流式布局
- **响应式**: 移动端录入页全宽单列、控件加大（min-h-12）；PC端双栏并排、标准尺寸控件

## 5. Visual Language (视觉语言)

- **形态参数**: 圆角 `rounded-lg (0.5rem)` · 阴影 `shadow-sm` · 间距基调 `standard`
- **识别签名**: 首页手动填写卡片蓝色实心填充略大于OCR卡片；统计数字 tabular-nums + font-semibold；区域标签带色彩圆点
- **装饰策略**: 仅用轻投影和微圆角表达洁净层次，无渐变/纹理/插画装饰
- **动效原则**: 表单提交成功绿色对勾淡入1.5s自动跳转；表格行审核通过绿色淡出；hover/focus 150ms
- **可及性**: 对比度 ≥ 4.5:1；状态标签同时用色彩+文字双重编码；交互元素有明确 focus ring；移动端触控目标 ≥ 44px

## 6. Component Principles (组件原则)

- **状态完整性**: Button/Input/Badge 覆盖五态；表单 Error 态红色边框+下方提示文字
- **层级清晰**: Primary 蓝色实心 vs Secondary 白色描边；Ghost 仅 hover 显示 accent 背景
- **一致性**: 所有卡片统一 p-6 + rounded-lg + shadow-sm；表格斑马纹用 bg-muted/30 交替
- **移动端适配**: 录入页按钮 min-h-12 + text-lg；输入框 min-h-12 + px-4；拍照/相册入口等大并排

## 7. Image Direction (图片与视觉资产，按需)

- **Image Role**: 无强制图片需求
- **Image Art Direction**: 优先通过排版、色彩和局部图形建立视觉记忆点；OCR上传区用虚线边框+相机图标暗示「等待投喂」
- **Image Prompt Keywords**: 无
- **Image Avoidance**: 禁止通用科技插图、商务人物素材、抽象渐变背景、装饰性插画

## 8. 应避免 (Anti-patterns)

- ❌ 使用高饱和大面积色块或渐变——破坏GMP洁净车间的专业克制感
- ❌ 录入页添加多余装饰/说明区块——违背「30秒极简录入」核心任务
- ❌ 状态仅靠颜色区分无文字标签——不符合制药行业无障碍与合规审计要求
- ❌ 移动端沿用PC端小尺寸控件或拖拽上传——违背车间现场触屏操作场景

## 9. 应用架构

### 功能模块

- **数据总表**: 统一管理所有物料数据（日期/物料名称/规格型号/数量/单位/供应商/备注），支持Excel导出、筛选、搜索、新增和删除
- **手动填写**: 矩阵表格录入（选区域→选日期→位点行×时段列，位点编号自动填充不可编辑，时段列标题可自定义编辑→批量提交）
- **OCR识别**: 后台静默识别（上传图片→创建任务→后台异步识别→通知推送→结果编辑提交）
- **数据记录**: 同一位点一行合并展示（列：位点编号/区域/08:00~18:00压差值/日期），多条件筛选+分页+单条删除+批量删除（带二次确认，仅管理员）+多Sheet Excel导出（按区域分Sheet）
- **位点管理**: 管理员CRUD位点映射库（位点编号+区域+标准压差）
- **审核管理**: 管理员审核/驳回记录，支持批量操作
- **通知系统**: 应用内通知铃铛（OCR完成/失败推送，未读计数，已读标记）

### 数据模型

- `data_master`: 数据总表（日期/物料名称/规格型号/数量/单位/供应商/备注/来源/创建人），所有录入方式的统一存储
- `pressure_record`: 压差记录（支持batch_id分组、time_slot班次标识仅旧数据使用）
- `point_mapping`: 位点映射（位点编号唯一，绑定区域和标准压差）
- `ocr_task`: OCR任务（状态：pending→processing→completed/failed/cancelled→submitted）
- `notification`: 通知（类型、已读状态、关联实体）

### 路由

| 路径 | 页面 | 说明 |
|------|------|------|
| / | HomePage | 首页仪表板 |
| /data-master | DataMasterPage | 数据总表（OCR上传+Excel风格表格+导出+删除） |
| /manual-input | ManualInputPage | 模板表格手动录入 |
| /ocr-input | OcrInputPage | OCR图片上传 |
| /ocr-result/:taskId | OcrResultPage | OCR结果编辑提交 |
| /records | RecordsPage | 数据记录+导出 |
| /point-management | PointManagementPage | 位点管理 |
| /audit-management | AuditManagementPage | 审核管理 |