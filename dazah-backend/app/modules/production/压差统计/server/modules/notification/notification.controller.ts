import { Controller, Get, Patch, Param, Req } from '@nestjs/common';
import { NeedLogin } from '@lark-apaas/fullstack-nestjs-core';
import { NotificationService } from './notification.service';
import type { NotificationListResponse } from '@shared/api.interface';

@Controller('api/notifications')
export class NotificationController {
  constructor(private readonly notificationService: NotificationService) {}

  @Get()
  @NeedLogin()
  async list(@Req() req: any): Promise<NotificationListResponse> {
    const userId: string = req.userContext?.userId ?? '';
    return this.notificationService.list(userId);
  }

  @Get('unread-count')
  @NeedLogin()
  async unreadCount(@Req() req: any): Promise<{ count: number }> {
    const userId: string = req.userContext?.userId ?? '';
    const count = await this.notificationService.getUnreadCount(userId);
    return { count };
  }

  @Patch(':id/read')
  @NeedLogin()
  async markRead(@Req() req: any, @Param('id') id: string): Promise<{ success: boolean }> {
    const userId: string = req.userContext?.userId ?? '';
    await this.notificationService.markRead(userId, id);
    return { success: true };
  }

  @Patch('read-all')
  @NeedLogin()
  async markAllRead(@Req() req: any): Promise<{ success: boolean }> {
    const userId: string = req.userContext?.userId ?? '';
    await this.notificationService.markAllRead(userId);
    return { success: true };
  }
}
