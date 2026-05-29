"""Tests for the matching engine module.

Test cases to implement:
- test_haversine_distance - Distance calculation accuracy
- test_calculate_score - Score calculation with all weight factors
- test_match_single_request - Matching one request to available drivers
- test_match_multiple_requests - Batch matching with fairness
- test_distance_threshold - Drivers outside radius are excluded
- test_no_available_drivers - Handle case with no drivers
- test_driver_capacity - Respects driver max_capacity
- test_fresh_evaluation - Each request re-evaluates all available drivers
"""
