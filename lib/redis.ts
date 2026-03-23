/**
 * lib/redis.ts — Upstash Redis client for session-level caching.
 *
 * Used to store in-progress iteration state keyed by thread_id.
 * The Upstash REST client works in both Node.js and Edge runtimes.
 */

import { Redis } from "@upstash/redis";

export const redis = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL!,
  token: process.env.UPSTASH_REDIS_REST_TOKEN!,
});

const SESSION_TTL_SECONDS = 3600; // 1 hour

export async function getSessionCache<T>(threadId: string): Promise<T | null> {
  return redis.get<T>(`session:${threadId}`);
}

export async function setSessionCache<T>(
  threadId: string,
  data: T,
  ttlSeconds = SESSION_TTL_SECONDS
): Promise<void> {
  await redis.setex(`session:${threadId}`, ttlSeconds, data as Parameters<typeof redis.setex>[2]);
}

export async function deleteSessionCache(threadId: string): Promise<void> {
  await redis.del(`session:${threadId}`);
}
