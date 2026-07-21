import { Injectable, Inject, Logger } from '@nestjs/common';
import { DRIZZLE_DATABASE, type PostgresJsDatabase } from '@lark-apaas/fullstack-nestjs-core';
import { notification } from '@server/database/schema';
import { eq, and, desc, count, sql } from 'drizzle-orm';
import type {
  NotificationItem,
  NotificationListResponse,
} from '@shared/api.interface';

@Injectable()
export class NotificationService {
  private readonly logger = new Logger(NotificationService.name);

  constructor(
    @Inject(DRIZZLE_DATABASE) private readonly db: PostgresJsDatabase,
  ) {}

  async create(params: {
    type: string;
    title: string;
    message: string;
    targetUser: string;
    relatedId?: string;
    relatedType?: string;
  }): Promise<void> {
    try {
      await this.db.insert(notification).values({
        type: params.type,
        title: params.title,
        message: params.message,
        targetUser: params.targetUser,
        relatedId: params.relatedId ?? null,
        relatedType: params.relatedType ?? null,
      });
    } catch (err) {
      this.logger.error(`Failed to create notification: ${JSON.stringify(err)}`);
    }
  }

  async list(userId: string): Promise<NotificationListResponse> {
    const [items, unreadResult] = await Promise.all([
      this.db
        .select({
          id: notification.id,
          type: notification.type,
          title: notification.title,
          message: notification.message,
          isRead: notification.isRead,
          relatedId: notification.relatedId,
          relatedType: notification.relatedType,
          createdAt: notification.createdAt,
        })
        .from(notification)
        .where(eq(notification.targetUser, userId))
        .orderBy(desc(notification.createdAt))
        .limit(50),
      this.db
        .select({ count: count() })
        .from(notification)
        .where(
          and(
            eq(notification.targetUser, userId),
            eq(notification.isRead, false),
          ),
        ),
    ]);

    const mappedItems: NotificationItem[] = items.map((item) => ({
      id: item.id,
      type: item.type,
      title: item.title,
      message: item.message,
      isRead: item.isRead,
      relatedId: item.relatedId,
      relatedType: item.relatedType,
      createdAt: item.createdAt.toISOString(),
    }));

    return {
      items: mappedItems,
      unreadCount: Number(unreadResult[0]?.count ?? 0),
    };
  }

  async markRead(userId: string, id: string): Promise<void> {
    await this.db
      .update(notification)
      .set({ isRead: true, updatedAt: new Date() })
      .where(
        and(
          eq(notification.id, id),
          eq(notification.targetUser, userId),
        ),
      );
  }

  async markAllRead(userId: string): Promise<void> {
    await this.db
      .update(notification)
      .set({ isRead: true, updatedAt: new Date() })
      .where(
        and(
          eq(notification.targetUser, userId),
          eq(notification.isRead, false),
        ),
      );
  }

  async getUnreadCount(userId: string): Promise<number> {
    const result = await this.db
      .select({ count: count() })
      .from(notification)
      .where(
        and(
          eq(notification.targetUser, userId),
          eq(notification.isRead, false),
        ),
      );
    return Number(result[0]?.count ?? 0);
  }
}
