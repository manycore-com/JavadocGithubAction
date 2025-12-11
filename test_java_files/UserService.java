package com.example.service;

import java.util.List;
import java.util.Optional;
import java.util.Map;
import java.util.HashMap;
import java.util.ArrayList;

/**
 * Service for managing user lifecycle operations including creation, retrieval, updates, and deactivation.
 * Provides caching layer for improved performance and supports batch operations with retry logic.
 * Integrates with email service for user notifications.
 * 
 * <p>Thread-safety: This service is not thread-safe due to the internal cache implementation.
 * Consider synchronization if used in concurrent environments.
 * 
 * @see UserRepository
 * @see EmailService
 */
public class UserService {

    private final Map<Long, User> userCache = new HashMap<>();
    private final UserRepository repository;
    private final EmailService emailService;

    /**
     * Creates a new UserService with the specified repository and email service.
     * Both dependencies are required for user management operations.
     *
     * @param repository the repository for user persistence operations
     * @param emailService the service for sending user-related emails
     */
    public UserService(UserRepository repository, EmailService emailService) {
        this.repository = repository;
        this.emailService = emailService;
    }

    /**
     * Finds a user by ID with optional inclusion of deleted users and selective field loading.
     * Results are cached for performance. Deleted users are filtered out by default unless
     * explicitly requested.
     *
     * @param id the user ID to search for
     * @param includeDeleted whether to include deleted users in the search results
     * @param fieldsToLoad specific fields to load from the repository (null loads all fields)
     * @return the user wrapped in Optional, or empty if not found or deleted (when includeDeleted is false)
     * @throws IllegalArgumentException if id is null or non-positive
     */
    public Optional<User> findUserById(Long id, boolean includeDeleted, List<String> fieldsToLoad) {
        if (id == null || id <= 0) {
            throw new IllegalArgumentException("Invalid user ID");
        }

        // Check cache first
        if (userCache.containsKey(id)) {
            User cached = userCache.get(id);
            if (!cached.isDeleted() || includeDeleted) {
                return Optional.of(cached);
            }
        }

        // Load from repository with specified fields
        Optional<User> user = repository.findById(id, fieldsToLoad);

        if (user.isPresent()) {
            User u = user.get();
            if (u.isDeleted() && !includeDeleted) {
                return Optional.empty();
            }
            userCache.put(id, u);
        }

        return user;
    }

    /**
     * Creates a new user in the system with validation and notification.
     * Validates email format and uniqueness before creating the user. Automatically sends
     * a welcome email and updates the user cache upon successful creation.
     *
     * @param email user's email address (must be valid format)
     * @param name user's display name
     * @param role user's role (defaults to STANDARD if null)
     * @param metadata additional user attributes (empty map if null)
     * @return the newly created and persisted User
     * @throws IllegalArgumentException if email is null or invalid format
     * @throws UserAlreadyExistsException if email already exists in the system
     */
    public User createUser(String email, String name, UserRole role, Map<String, Object> metadata) {
        // Validate email format
        if (email == null || !email.matches("^[A-Za-z0-9+_.-]+@(.+)$")) {
            throw new IllegalArgumentException("Invalid email format");
        }

        // Check for existing user
        if (repository.existsByEmail(email)) {
            throw new UserAlreadyExistsException("User with email " + email + " already exists");
        }

        // Create user entity
        User user = new User();
        user.setEmail(email);
        user.setName(name);
        user.setRole(role != null ? role : UserRole.STANDARD);
        user.setMetadata(metadata != null ? metadata : new HashMap<>());
        user.setCreatedAt(System.currentTimeMillis());

        // Persist and send welcome email
        User savedUser = repository.save(user);
        emailService.sendWelcomeEmail(savedUser);

        // Update cache
        userCache.put(savedUser.getId(), savedUser);

        return savedUser;
    }

    /**
     * Processes a batch of user updates with automatic retry logic and configurable error handling.
     * Each update is attempted up to maxRetries times with exponential backoff between attempts.
     * Updates are processed sequentially, and results are collected for all attempted updates.
     *
     * @param updates list of user updates to apply
     * @param maxRetries maximum number of attempts per update (must be at least 1)
     * @param stopOnError if true, stops processing remaining updates after the first failure
     * @return list of results indicating success/failure for each update attempt
     */
    public List<BatchUpdateResult> processBatchUpdates(List<UserUpdate> updates, int maxRetries, boolean stopOnError) {
        List<BatchUpdateResult> results = new ArrayList<>();

        for (UserUpdate update : updates) {
            int attempts = 0;
            boolean success = false;
            Exception lastError = null;

            while (attempts < maxRetries && !success) {
                try {
                    attempts++;
                    applyUpdate(update);
                    success = true;
                    results.add(new BatchUpdateResult(update.getUserId(), true, null));
                } catch (Exception e) {
                    lastError = e;
                    if (attempts < maxRetries) {
                        try {
                            Thread.sleep(100 * attempts); // Exponential backoff
                        } catch (InterruptedException ie) {
                            Thread.currentThread().interrupt();
                            break;
                        }
                    }
                }
            }

            if (!success) {
                results.add(new BatchUpdateResult(update.getUserId(), false, lastError.getMessage()));
                if (stopOnError) {
                    break;
                }
            }
        }

        return results;
    }

    private void applyUpdate(UserUpdate update) {
        User user = repository.findById(update.getUserId())
            .orElseThrow(() -> new UserNotFoundException("User not found: " + update.getUserId()));

        if (update.getName() != null) {
            user.setName(update.getName());
        }
        if (update.getEmail() != null) {
            user.setEmail(update.getEmail());
        }
        if (update.getRole() != null) {
            user.setRole(update.getRole());
        }

        repository.save(user);
        userCache.put(user.getId(), user);
    }

    /**
     * Deactivates users who haven't logged in within the specified threshold.
     * Only non-admin, non-deleted users are affected. Deactivated users are removed from cache.
     *
     * @param inactiveDaysThreshold number of days of inactivity before deactivation
     * @param sendNotification whether to send email notifications to deactivated users
     */
    public void deactivateInactiveUsers(long inactiveDaysThreshold, boolean sendNotification) {
        long cutoffTime = System.currentTimeMillis() - (inactiveDaysThreshold * 24 * 60 * 60 * 1000);

        List<User> inactiveUsers = repository.findByLastLoginBefore(cutoffTime);

        for (User user : inactiveUsers) {
            if (!user.isDeleted() && user.getRole() != UserRole.ADMIN) {
                user.setActive(false);
                repository.save(user);
                userCache.remove(user.getId());

                if (sendNotification) {
                    emailService.sendDeactivationNotice(user);
                }
            }
        }
    }
}
