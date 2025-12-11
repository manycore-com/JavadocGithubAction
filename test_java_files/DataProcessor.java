package com.example.processing;

import java.util.List;
import java.util.ArrayList;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.stream.Collectors;

/**
 * A robust data processing engine that handles batch processing, retries, and asynchronous operations.
 * 
 * This class provides fault-tolerant data transformation capabilities with configurable retry strategies,
 * batch processing for large datasets, and comprehensive metrics collection. It supports both synchronous
 * processing with retry logic and asynchronous processing for improved throughput.
 * 
 * The processor validates all items before transformation and collects metrics on success, failure,
 * and retry rates. Results are returned with both successful transformations and detailed error information.
 * 
 * Thread-safe when used with a properly configured ExecutorService.
 */
public class DataProcessor {

    private final ExecutorService executor;
    private final int batchSize;
    private final DataValidator validator;
    private final MetricsCollector metrics;

    /**
     * Constructs a DataProcessor with the specified execution and validation components.
     * 
     * @param executor the thread pool for asynchronous processing operations
     * @param batchSize the number of items to process in each batch
     * @param validator validates items before processing
     * @param metrics collects processing statistics and performance data
     */
    public DataProcessor(ExecutorService executor, int batchSize, DataValidator validator, MetricsCollector metrics) {
        this.executor = executor;
        this.batchSize = batchSize;
        this.validator = validator;
        this.metrics = metrics;
    }

    /**
     * Processes a list of items with automatic retry capability on failures.
     * 
     * Items are processed in batches determined by the configured batch size. Each item is validated
     * before transformation, and failed items are retried according to the specified strategy.
     * Processing continues even if individual items fail, collecting both successful results and errors.
     * Metrics are recorded throughout the process including retries, successes, and failures.
     *
     * @param <T> the type of input items to process
     * @param <R> the type of transformed result
     * @param items the list of items to process
     * @param transformer the function to transform each item
     * @param maxRetries maximum retry attempts per item before marking as failed
     * @param strategy determines the delay between retry attempts
     * @return a result containing all successful transformations, errors, and total processing time
     */
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

    /**
     * Asynchronously processes a list of items, transforming valid items and handling errors.
     * Items are validated before transformation, with failed validations and transformation
     * errors delegated to the provided error handler. Null transformation results are silently
     * filtered from the output.
     *
     * @param items the items to process
     * @param transformer converts each valid item to a result
     * @param errorHandler handles validation failures and transformation exceptions
     * @param <T> the type of input items
     * @param <R> the type of transformation results
     * @return a future containing successfully transformed results (excludes nulls and errors)
     */
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

    /**
     * Transforms an input of type T into an output of type R.
     * 
     * @param <T> the type of the input to be transformed
     * @param <R> the type of the transformation result
     */
    public interface Transformer<T, R> {
        R transform(T input) throws Exception;
    }

    /**
     * Defines callbacks for handling errors during data processing operations.
     * Implementations should provide appropriate error handling strategies for both
     * validation failures and transformation exceptions.
     *
     * @param <T> the type of items being processed
     */
    public interface ErrorHandler<T> {
        void handleValidationError(T item, String message);
        void handleTransformError(T item, Exception e);
    }

    /**
     * Defines a strategy for calculating retry delays between failed processing attempts.
     * Implementations determine the timing behavior for retries, such as fixed delays,
     * linear backoff, or exponential backoff patterns.
     */
    public interface RetryStrategy {
        long calculateDelay(int attemptNumber);
    }

    /**
     * Implements an exponential backoff retry strategy where delays increase exponentially between attempts.
     * 
     * Each retry delay is calculated as baseDelayMs * (multiplier ^ (attemptNumber - 1)).
     * For example, with baseDelayMs=100 and multiplier=2, delays would be: 100ms, 200ms, 400ms, 800ms...
     */
    public static class ExponentialBackoff implements RetryStrategy {
        private final long baseDelayMs;
        private final double multiplier;

        /**
         * Creates an ExponentialBackoff retry strategy with configurable delay parameters.
         *
         * @param baseDelayMs initial delay in milliseconds before the first retry
         * @param multiplier factor by which the delay increases with each subsequent attempt
         */
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
