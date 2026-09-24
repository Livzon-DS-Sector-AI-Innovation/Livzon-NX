# 独立列表页的 URL 状态与详情返回

适用于有独立路由的台账、任务或记录列表。已提交的筛选、排序、页码和每页条数
由 URL 查询参数保存；输入框未提交的草稿可以暂存在组件状态。URL 不得包含凭据
或敏感信息。一个页面有多个表格时，先为各表使用明确的参数前缀，避免互相覆盖。

## 当前项目入口

- Client Component 使用 `src/lib/useListUrlState.ts` 的 `useListUrlState()`。
  `setListQuery(patch, true)` 提交筛选、排序或页大小并重置页码；单纯翻页使用
  `setListQuery(patch)`。它会保留页面已有的其他查询参数。
- Server Component 使用 `src/lib/list-url-state.ts` 的 `readListPagination(query)`
  校验首屏分页，再用同一组筛选参数请求后端。不要让首屏固定请求第一页，随后
  再由客户端切换到 URL 指定页。
- 进入详情、编辑或新建页时，使用 `detailHref(detailPath)` 携带当前列表地址。
  返回时使用 `getSafeListReturnHref(returnTo, currentPath, expectedListPath)` 校验
  同源相对路径和所属列表；校验失败回到该模块的默认列表路由。面包屑的列表层级
  也应使用这个地址，不依赖 `router.back()`、全局 store 或浏览器持久化存储。

```tsx
const { page, pageSize, setListQuery, detailHref } = useListUrlState(20)
setListQuery({ status }, true)                         // 提交筛选，回第一页
setListQuery({ page, page_size: pageSize })            // 翻页，保留筛选
router.push(detailHref(`/safety/scheduled-tasks/${id}`))

// app/(dashboard)/safety/scheduled-tasks/page.tsx
const query = await searchParams
const { page, pageSize } = readListPagination(query)
```

重置查询时同步删除 URL 条件；筛选、排序或页大小变化时回第一页。改造旧页时
保持现有 API 参数和权限判断不变。测试至少覆盖筛选后页码重置、翻页与页大小
保留、刷新或详情返回恢复、无效参数回退，以及其他业务查询参数不丢失。
