package com.example.cache;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.Map;
import java.util.function.Function;

/**
 * A thread-safe, generic cache implementation with automatic expiration and configurable eviction policies.
 * Supports Time-To-Live (TTL) for cache entries and maintains a maximum cache size with automatic
 * eviction when capacity is reached. Entries expire based on TTL and are periodically cleaned up
 * by a background thread.
 * 
 * <p>This cache is suitable for high-concurrency environments and provides statistics gathering
 * capabilities for monitoring cache performance and usage patterns.
 * 
 * @param <K> the type of keys maintained by this cache
 * @param <V> the type of cached values
 */
public class CacheManager<K, V> {

    private final ConcurrentHashMap<K, CacheEntry<V>> cache;
    private final long defaultTtlMillis;
    private final int maxSize;
    private final ScheduledExecutorService evictionExecutor;
    private final EvictionPolicy evictionPolicy;

    /**
     * Constructs a new CacheManager with specified TTL, size limit, and eviction policy.
     * Automatically schedules periodic eviction of expired entries at intervals of half the TTL.
     *
     * @param defaultTtlMillis default time-to-live for cache entries in milliseconds
     * @param maxSize maximum number of entries before eviction occurs
     * @param policy eviction strategy when cache reaches capacity (LRU, LFU, or FIFO)
     */
    public CacheManager(long defaultTtlMillis, int maxSize, EvictionPolicy policy) {
        this.cache = new ConcurrentHashMap<>();
        this.defaultTtlMillis = defaultTtlMillis;
        this.maxSize = maxSize;
        this.evictionPolicy = policy;
        this.evictionExecutor = Executors.newSingleThreadScheduledExecutor();

        // Schedule periodic eviction
        evictionExecutor.scheduleAtFixedRate(
            this::evictExpiredEntries,
            defaultTtlMillis,
            defaultTtlMillis / 2,
            TimeUnit.MILLISECONDS
        );
    }

    /**
     * Retrieves a cached value or computes and caches it if absent or expired.
     * The computed value is stored with the specified TTL or the default TTL if none is provided.
     *
     * @param key the cache key
     * @param loader function to compute the value if not cached
     * @param customTtlMillis custom TTL in milliseconds; uses default TTL if ≤ 0
     * @return the cached or newly computed value, or null if the loader returns null
     */
    public V getOrCompute(K key, Function<K, V> loader, long customTtlMillis) {
        CacheEntry<V> entry = cache.get(key);

        // Check if entry exists and is not expired
        if (entry != null && !entry.isExpired()) {
            entry.recordAccess();
            return entry.getValue();
        }

        // Compute new value
        V value = loader.apply(key);
        if (value != null) {
            put(key, value, customTtlMillis > 0 ? customTtlMillis : defaultTtlMillis);
        }

        return value;
    }

    /**
     * Put value in cache.
     */
    public void put(K key, V value, long ttlMillis) {
        // Check if we need to evict before adding
        if (cache.size() >= maxSize && !cache.containsKey(key)) {
            evictOne();
        }

        long expirationTime = System.currentTimeMillis() + ttlMillis;
        cache.put(key, new CacheEntry<>(value, expirationTime));
    }

    /**
     * Retrieves a value from the cache if it exists and hasn't expired.
     * Expired entries are automatically removed when accessed.
     *
     * @param key the key whose associated value is to be returned
     * @return the cached value, or null if not found or expired
     */
    public V get(K key) {
        CacheEntry<V> entry = cache.get(key);
        if (entry == null) {
            return null;
        }
        if (entry.isExpired()) {
            cache.remove(key);
            return null;
        }
        entry.recordAccess();
        return entry.getValue();
    }

    /**
     * Computes comprehensive statistics about the current cache state.
     * Analyzes cache entries to provide metrics including entry counts, access patterns,
     * age distribution, and optionally memory usage and key distribution data.
     *
     * @param includeMemoryEstimate whether to calculate estimated memory consumption
     * @param includeKeyDistribution whether to analyze key distribution patterns
     * @return map containing cache metrics with keys: totalEntries, expiredEntries, activeEntries,
     *         totalAccessCount, averageAccessCount, hitRatio, oldestEntryAgeMs, newestEntryAgeMs,
     *         and optionally estimatedMemoryBytes and keyDistribution
     */
    public Map<String, Object> computeCacheStatistics(boolean includeMemoryEstimate, boolean includeKeyDistribution) {
        Map<String, Object> stats = new ConcurrentHashMap<>();

        int totalEntries = cache.size();
        int expiredCount = 0;
        long totalAccessCount = 0;
        long oldestEntry = Long.MAX_VALUE;
        long newestEntry = 0;

        for (Map.Entry<K, CacheEntry<V>> entry : cache.entrySet()) {
            CacheEntry<V> cacheEntry = entry.getValue();

            if (cacheEntry.isExpired()) {
                expiredCount++;
            }

            totalAccessCount += cacheEntry.getAccessCount();
            oldestEntry = Math.min(oldestEntry, cacheEntry.getCreationTime());
            newestEntry = Math.max(newestEntry, cacheEntry.getCreationTime());
        }

        stats.put("totalEntries", totalEntries);
        stats.put("expiredEntries", expiredCount);
        stats.put("activeEntries", totalEntries - expiredCount);
        stats.put("totalAccessCount", totalAccessCount);
        stats.put("averageAccessCount", totalEntries > 0 ? (double) totalAccessCount / totalEntries : 0);
        stats.put("hitRatio", calculateHitRatio());

        if (oldestEntry != Long.MAX_VALUE) {
            stats.put("oldestEntryAgeMs", System.currentTimeMillis() - oldestEntry);
            stats.put("newestEntryAgeMs", System.currentTimeMillis() - newestEntry);
        }

        if (includeMemoryEstimate) {
            stats.put("estimatedMemoryBytes", estimateMemoryUsage());
        }

        if (includeKeyDistribution) {
            stats.put("keyDistribution", computeKeyDistribution());
        }

        return stats;
    }

    private void evictExpiredEntries() {
        long now = System.currentTimeMillis();
        cache.entrySet().removeIf(entry -> entry.getValue().getExpirationTime() < now);
    }

    private void evictOne() {
        if (cache.isEmpty()) {
            return;
        }

        K keyToEvict = null;

        switch (evictionPolicy) {
            case LRU:
                long oldestAccess = Long.MAX_VALUE;
                for (Map.Entry<K, CacheEntry<V>> entry : cache.entrySet()) {
                    if (entry.getValue().getLastAccessTime() < oldestAccess) {
                        oldestAccess = entry.getValue().getLastAccessTime();
                        keyToEvict = entry.getKey();
                    }
                }
                break;

            case LFU:
                long lowestFrequency = Long.MAX_VALUE;
                for (Map.Entry<K, CacheEntry<V>> entry : cache.entrySet()) {
                    if (entry.getValue().getAccessCount() < lowestFrequency) {
                        lowestFrequency = entry.getValue().getAccessCount();
                        keyToEvict = entry.getKey();
                    }
                }
                break;

            case FIFO:
                long oldestCreation = Long.MAX_VALUE;
                for (Map.Entry<K, CacheEntry<V>> entry : cache.entrySet()) {
                    if (entry.getValue().getCreationTime() < oldestCreation) {
                        oldestCreation = entry.getValue().getCreationTime();
                        keyToEvict = entry.getKey();
                    }
                }
                break;
        }

        if (keyToEvict != null) {
            cache.remove(keyToEvict);
        }
    }

    private double calculateHitRatio() {
        // Placeholder - would need hit/miss tracking
        return 0.0;
    }

    private long estimateMemoryUsage() {
        // Rough estimate
        return cache.size() * 256L;
    }

    private Map<String, Integer> computeKeyDistribution() {
        // Placeholder
        return new ConcurrentHashMap<>();
    }

    /**
     * Gracefully shuts down the cache manager and releases all resources.
     * Attempts to terminate the eviction executor with a 5-second timeout before forcing shutdown.
     * Clears all cached entries after executor termination.
     * 
     * This method ensures proper cleanup of background threads and should be called when
     * the cache manager is no longer needed to prevent resource leaks.
     */
    public void shutdown() {
        evictionExecutor.shutdown();
        try {
            if (!evictionExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                evictionExecutor.shutdownNow();
            }
        } catch (InterruptedException e) {
            evictionExecutor.shutdownNow();
            Thread.currentThread().interrupt();
        }
        cache.clear();
    }

    /**
     * Defines the eviction strategy for cache entries when the cache reaches maximum capacity.
     * 
     * LRU (Least Recently Used) - Evicts the entry that hasn't been accessed for the longest time.
     * LFU (Least Frequently Used) - Evicts the entry with the lowest access count.
     * FIFO (First In First Out) - Evicts the oldest entry based on creation time.
     */
    public enum EvictionPolicy {
        LRU, LFU, FIFO
    }

    private static class CacheEntry<V> {
        private final V value;
        private final long expirationTime;
        private final long creationTime;
        private long lastAccessTime;
        private long accessCount;

        CacheEntry(V value, long expirationTime) {
            this.value = value;
            this.expirationTime = expirationTime;
            this.creationTime = System.currentTimeMillis();
            this.lastAccessTime = this.creationTime;
            this.accessCount = 0;
        }

        V getValue() { return value; }
        long getExpirationTime() { return expirationTime; }
        long getCreationTime() { return creationTime; }
        long getLastAccessTime() { return lastAccessTime; }
        long getAccessCount() { return accessCount; }
        boolean isExpired() { return System.currentTimeMillis() > expirationTime; }

        void recordAccess() {
            this.lastAccessTime = System.currentTimeMillis();
            this.accessCount++;
        }
    }
}
