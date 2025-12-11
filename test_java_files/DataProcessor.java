package com.example.processing;

import java.util.List;
import java.util.ArrayList;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.stream.Collectors;

/**
 * Processes data.
 */
public class DataProcessor {

    private final ExecutorService executor;
    private final int batchSize;
    private final DataValidator validator;
    private final MetricsCollector metrics;

    public DataProcessor(ExecutorService executor, int batchSize, DataValidator validator, MetricsCollector metrics) {
        this.executor = executor;
        this.batchSize = batchSize;
        this.validator = validator;
        this.metrics = metrics;
    }

    public <T, R> ProcessingResult<R> processWithRetry(
            List<T> items,
            Transformer<T, R> transformer,
            int maxRetries,
            RetryStrategy strategy) {

        List<R> successfulResults = new ArrayList<>();
        List<ProcessingError> errors = new ArrayList<>();
        long startTime = System.currentTimeMillis();

        // Split into batches
        List<List<T>> batches = splitIntoBatches(items);
        metrics.recordBatchCount(batches.size());

        for (int batchIndex = 0; batchIndex < batches.size(); batchIndex++) {
            List<T> batch = batches.get(batchIndex);

            for (T item : batch) {
                int attempts = 0;
                R result = null;
                Exception lastException = null;

                while (attempts < maxRetries) {
                    attempts++;
                    try {
                        // Validate before processing
                        if (!validator.isValid(item)) {
                            throw new ValidationException("Item failed validation");
                        }

                        result = transformer.transform(item);
                        successfulResults.add(result);
                        metrics.recordSuccess();
                        break;

                    } catch (Exception e) {
                        lastException = e;
                        metrics.recordRetry();

                        if (attempts < maxRetries) {
                            long delay = strategy.calculateDelay(attempts);
                            try {
                                Thread.sleep(delay);
                            } catch (InterruptedException ie) {
                                Thread.currentThread().interrupt();
                                errors.add(new ProcessingError(item, "Interrupted during retry"));
                                break;
                            }
                        }
                    }
                }

                if (result == null && lastException != null) {
                    errors.add(new ProcessingError(item, lastException.getMessage()));
                    metrics.recordFailure();
                }
            }
        }

        long duration = System.currentTimeMillis() - startTime;
        metrics.recordProcessingTime(duration);

        return new ProcessingResult<>(successfulResults, errors, duration);
    }

    public <T, R> CompletableFuture<List<R>> processAsync(
            List<T> items,
            Transformer<T, R> transformer,
            ErrorHandler<T> errorHandler) {

        return CompletableFuture.supplyAsync(() -> {
            List<R> results = new ArrayList<>();

            for (T item : items) {
                try {
                    if (validator.isValid(item)) {
                        R result = transformer.transform(item);
                        if (result != null) {
                            results.add(result);
                        }
                    } else {
                        errorHandler.handleValidationError(item, "Validation failed");
                    }
                } catch (Exception e) {
                    errorHandler.handleTransformError(item, e);
                }
            }

            return results;
        }, executor);
    }

    /**
     * Merges multiple processing results into a single consolidated result.
     *
     * This method takes a list of individual ProcessingResult objects and combines
     * them into one unified result. All successful results are aggregated into a
     * single list, and all errors from each result are collected together.
     *
     * @param results The list of ProcessingResult objects to merge together
     * @param <R> The type of the successful result items
     * @return A new ProcessingResult containing all successes and errors from the input results
     */
    public <R> ProcessingResult<R> mergeResults(List<ProcessingResult<R>> results) {
        List<R> allSuccesses = new ArrayList<>();
        List<ProcessingError> allErrors = new ArrayList<>();
        long totalDuration = 0;

        for (ProcessingResult<R> result : results) {
            allSuccesses.addAll(result.getSuccessful());
            allErrors.addAll(result.getErrors());
            totalDuration += result.getDurationMs();
        }

        return new ProcessingResult<>(allSuccesses, allErrors, totalDuration);
    }

    private <T> List<List<T>> splitIntoBatches(List<T> items) {
        List<List<T>> batches = new ArrayList<>();
        for (int i = 0; i < items.size(); i += batchSize) {
            int end = Math.min(i + batchSize, items.size());
            batches.add(new ArrayList<>(items.subList(i, end)));
        }
        return batches;
    }

    public interface Transformer<T, R> {
        R transform(T input) throws Exception;
    }

    public interface ErrorHandler<T> {
        void handleValidationError(T item, String message);
        void handleTransformError(T item, Exception e);
    }

    public interface RetryStrategy {
        long calculateDelay(int attemptNumber);
    }

    public static class ExponentialBackoff implements RetryStrategy {
        private final long baseDelayMs;
        private final double multiplier;

        public ExponentialBackoff(long baseDelayMs, double multiplier) {
            this.baseDelayMs = baseDelayMs;
            this.multiplier = multiplier;
        }

        @Override
        public long calculateDelay(int attemptNumber) {
            return (long) (baseDelayMs * Math.pow(multiplier, attemptNumber - 1));
        }
    }
}
