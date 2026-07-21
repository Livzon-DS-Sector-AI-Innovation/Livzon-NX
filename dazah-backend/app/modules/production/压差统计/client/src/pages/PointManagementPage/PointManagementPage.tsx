import React, { useCallback, useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { Plus, Pencil, Trash2, Search } from 'lucide-react';
import { toast } from 'sonner';
import { logger } from '@lark-apaas/client-toolkit/logger';
import type { AreaType, PointMapping } from '@shared/api.interface';
import { AREA_OPTIONS } from '@shared/api.interface';
import {
  getPointMappingList,
  checkPointUnique,
  createPointMapping,
  updatePointMapping,
  deletePointMapping,
} from '@client/src/api';
import { Button } from '@client/src/components/ui/button';
import { Input } from '@client/src/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@client/src/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@client/src/components/ui/dialog';
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from '@client/src/components/ui/form';

const AREA_DOT_COLOR: Record<AreaType, string> = {
  '无菌区': 'bg-blue-500',
  '精洗区': 'bg-green-500',
  '配液区': 'bg-orange-500',
  '走廊': 'bg-yellow-500',
  '更衣室': 'bg-purple-500',
  '其他': 'bg-gray-400',
};

const pointFormSchema = z.object({
  pointId: z.string().min(1, '位点编号不能为空'),
  area: z.string().min(1, '请选择所属区域'),
  standardPressure: z.coerce.number({ invalid_type_error: '请输入数字' }),
});

type PointFormData = z.infer<typeof pointFormSchema>;

const FORM_DEFAULTS: PointFormData = {
  pointId: '',
  area: '',
  standardPressure: 0,
};

const PAGE_SIZE = 20;

const PointManagementPage: React.FC = () => {
  const [items, setItems] = useState<PointMapping[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [areaFilter, setAreaFilter] = useState('');

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<PointMapping | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingItem, setDeletingItem] = useState<PointMapping | null>(null);
  const [deleting, setDeleting] = useState(false);

  const form = useForm<PointFormData>({
    resolver: zodResolver(pointFormSchema),
    defaultValues: FORM_DEFAULTS,
  });

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, pageSize: PAGE_SIZE };
      if (keyword) params.keyword = keyword;
      if (areaFilter) params.area = areaFilter;
      const res = await getPointMappingList(params);
      setItems(res.items);
      setTotal(res.total);
    } catch (error) {
      logger.error('获取位点列表失败', error);
      toast.error('获取位点列表失败');
    } finally {
      setLoading(false);
    }
  }, [page, keyword, areaFilter]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const handleSearch = () => {
    setPage(1);
    fetchList();
  };

  const handleAreaFilterChange = (value: string) => {
    const val = value === '__all__' ? '' : value;
    setAreaFilter(val);
    setPage(1);
  };

  const openCreateDialog = () => {
    setEditingItem(null);
    form.reset(FORM_DEFAULTS);
    setDialogOpen(true);
  };

  const openEditDialog = (item: PointMapping) => {
    setEditingItem(item);
    form.reset({
      pointId: item.pointId,
      area: item.area,
      standardPressure: item.standardPressure,
    });
    setDialogOpen(true);
  };

  const handleFormSubmit = async (data: PointFormData) => {
    setSubmitting(true);
    try {
      if (!editingItem) {
        const uniqueRes = await checkPointUnique(data.pointId);
        if (uniqueRes.exists) {
          form.setError('pointId', { message: '该编号已存在' });
          setSubmitting(false);
          return;
        }
        await createPointMapping({
          pointId: data.pointId,
          area: data.area as AreaType,
          standardPressure: data.standardPressure,
        });
        toast.success('位点创建成功');
      } else {
        await updatePointMapping(editingItem.id, {
          pointId: data.pointId,
          area: data.area as AreaType,
          standardPressure: data.standardPressure,
        });
        toast.success('位点更新成功');
      }
      setDialogOpen(false);
      fetchList();
    } catch (error) {
      logger.error('保存位点失败', error);
      toast.error('保存位点失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  const openDeleteDialog = (item: PointMapping) => {
    setDeletingItem(item);
    setDeleteDialogOpen(true);
  };

  const handleDelete = async () => {
    if (!deletingItem) return;
    setDeleting(true);
    try {
      await deletePointMapping(deletingItem.id);
      toast.success('删除成功');
      setDeleteDialogOpen(false);
      setDeletingItem(null);
      fetchList();
    } catch (error) {
      logger.error('删除位点失败', error);
      toast.error('删除失败，请重试');
    } finally {
      setDeleting(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="min-h-screen bg-background p-4 sm:p-6">
      <div className="mx-auto max-w-[1400px]">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-xl font-bold text-foreground sm:text-2xl">
            位点管理
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            管理位点编号与区域、房间名称、标准压差的映射关系
          </p>
        </div>

        {/* Toolbar */}
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative max-w-xs flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="搜索位点编号..."
                value={keyword}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setKeyword(e.target.value)
                }
                onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => {
                  if (e.key === 'Enter') handleSearch();
                }}
                className="pl-9"
              />
            </div>
            <Select
              value={areaFilter || '__all__'}
              onValueChange={handleAreaFilterChange}
            >
              <SelectTrigger className="w-full sm:w-[160px]">
                <SelectValue placeholder="全部区域" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">全部区域</SelectItem>
                {AREA_OPTIONS.map((area: AreaType) => (
                  <SelectItem key={area} value={area}>
                    {area}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={openCreateDialog} className="gap-2">
            <Plus className="size-4" />
            新建位点
          </Button>
        </div>

        {/* Table */}
        <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px] text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    位点编号
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    所属区域
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    标准压差(Pa)
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-12 text-center text-muted-foreground"
                    >
                      加载中...
                    </td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-12 text-center text-muted-foreground"
                    >
                      暂无位点数据
                    </td>
                  </tr>
                ) : (
                  items.map((item: PointMapping, idx: number) => (
                    <tr
                      key={item.id}
                      className={
                        idx % 2 === 1 ? 'bg-muted/30' : ''
                      }
                    >
                      <td className="px-4 py-3 font-medium text-foreground">
                        {item.pointId}
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1.5">
                          <span
                            className={`inline-block h-2 w-2 rounded-full ${AREA_DOT_COLOR[item.area] || 'bg-gray-400'}`}
                          />
                          <span className="text-foreground">{item.area}</span>
                        </span>
                      </td>
                      <td className="px-4 py-3 text-foreground">
                        {item.standardPressure}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <button
                            type="button"
                            onClick={() => openEditDialog(item)}
                            className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                          >
                            <Pencil className="size-3.5" />
                            编辑
                          </button>
                          <button
                            type="button"
                            onClick={() => openDeleteDialog(item)}
                            className="inline-flex items-center gap-1 text-sm text-destructive hover:underline"
                          >
                            <Trash2 className="size-3.5" />
                            删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between border-t border-border px-4 py-3">
              <span className="text-sm text-muted-foreground">
                共 {total} 条，第 {page}/{totalPages} 页
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p: number) => Math.max(1, p - 1))}
                >
                  上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() =>
                    setPage((p: number) => Math.min(totalPages, p + 1))
                  }
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingItem ? '编辑位点' : '新建位点'}
            </DialogTitle>
            <DialogDescription>
              {editingItem
                ? '修改位点的映射关系信息'
                : '添加新的位点映射关系'}
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(handleFormSubmit)}
              className="space-y-4"
            >
              <FormField
                control={form.control}
                name="pointId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      位点编号 <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input
                        placeholder="例如: DP-001"
                        {...field}
                        disabled={!!editingItem}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="area"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      所属区域 <span className="text-destructive">*</span>
                    </FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      value={field.value}
                    >
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="请选择区域" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {AREA_OPTIONS.map((area: AreaType) => (
                          <SelectItem key={area} value={area}>
                            {area}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="standardPressure"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      标准压差 <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <div className="relative">
                        <Input
                          type="number"
                          placeholder="请输入标准压差"
                          {...field}
                          className="pr-10"
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                          Pa
                        </span>
                      </div>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setDialogOpen(false)}
                >
                  取消
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting ? '保存中...' : '保存'}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确认删除位点 {deletingItem?.pointId}{' '}
              的映射关系？此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDeleteDialogOpen(false);
                setDeletingItem(null);
              }}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? '删除中...' : '确认删除'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default PointManagementPage;
