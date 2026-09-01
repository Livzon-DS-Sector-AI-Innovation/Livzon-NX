import { redirect } from 'next/navigation'

// 仓储设置已合并至 /warehouse/settings（页面映射 + 飞书数据源二合一），
// 旧地址保留重定向以兼容历史书签
export default function WarehouseFeishuConfigRedirect() {
  redirect('/warehouse/settings')
}
