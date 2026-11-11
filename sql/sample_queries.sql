-- Campus Ride Match: course demonstration queries
-- These statements run directly against a database created by schema.sql.

-- 1. Multi-condition trip search with inclusive time-range overlap.
SELECT t.id, t.trip_date, t.start_time, t.end_time,
       oa.name AS origin_area, da.name AS destination_area,
       u.display_name AS publisher_name, t.available_seats
FROM trips AS t
JOIN users AS u ON u.id = t.publisher_id
JOIN location_areas AS oa ON oa.id = t.origin_area_id
JOIN location_areas AS da ON da.id = t.destination_area_id
WHERE t.trip_date >= date('now')
  AND t.origin_area_id = 1
  AND t.destination_area_id = 2
  AND t.start_time <= '19:00'
  AND t.end_time >= '17:00'
  AND t.status = 'Open'
  AND t.available_seats > 0
ORDER BY t.trip_date, t.start_time;

-- 2. Accepted participants with their request and user records.
SELECT t.id AS trip_id, u.display_name, u.email,
       mr.status AS request_status, tp.status AS participation_status,
       tp.joined_at
FROM trips AS t
JOIN trip_participants AS tp ON tp.trip_id = t.id
JOIN users AS u ON u.id = tp.user_id
JOIN match_requests AS mr ON mr.id = tp.request_id
WHERE t.id = 4
ORDER BY tp.joined_at;

-- 3. Incoming requests for trips published by user 1.
SELECT mr.id, mr.status, requester.display_name AS requester_name,
       t.trip_date, oa.name AS origin_area, da.name AS destination_area
FROM match_requests AS mr
JOIN trips AS t ON t.id = mr.trip_id
JOIN users AS requester ON requester.id = mr.requester_id
JOIN location_areas AS oa ON oa.id = t.origin_area_id
JOIN location_areas AS da ON da.id = t.destination_area_id
WHERE t.publisher_id = 1
ORDER BY CASE mr.status WHEN 'Pending' THEN 0 ELSE 1 END,
         mr.created_at DESC;

-- 4. All trips joined by user 2, including historical participation.
SELECT t.id, t.trip_date, t.status AS trip_status,
       tp.status AS participation_status,
       publisher.display_name AS publisher_name,
       oa.name AS origin_area, da.name AS destination_area
FROM trip_participants AS tp
JOIN trips AS t ON t.id = tp.trip_id
JOIN users AS publisher ON publisher.id = t.publisher_id
JOIN location_areas AS oa ON oa.id = t.origin_area_id
JOIN location_areas AS da ON da.id = t.destination_area_id
WHERE tp.user_id = 2
ORDER BY t.trip_date DESC, t.start_time;

-- 5. Average rating and review count for every user, including unrated users.
SELECT u.id, u.display_name,
       ROUND(AVG(r.rating), 2) AS average_rating,
       COUNT(r.id) AS review_count
FROM users AS u
LEFT JOIN reviews AS r ON r.reviewee_id = u.id
GROUP BY u.id, u.display_name
ORDER BY average_rating DESC, review_count DESC, u.display_name;

-- 6. Most common routes (two area joins plus GROUP BY aggregation).
SELECT oa.name AS origin_area, da.name AS destination_area,
       COUNT(*) AS trip_count
FROM trips AS t
JOIN location_areas AS oa ON oa.id = t.origin_area_id
JOIN location_areas AS da ON da.id = t.destination_area_id
GROUP BY t.origin_area_id, t.destination_area_id, oa.name, da.name
ORDER BY trip_count DESC, origin_area, destination_area
LIMIT 10;

-- 7. Lifecycle distribution of trips.
SELECT status, COUNT(*) AS trip_count
FROM trips
GROUP BY status
ORDER BY trip_count DESC, status;

-- 8. Open trips user 2 has neither joined nor actively requested.
SELECT t.id, t.trip_date, t.start_time, t.end_time
FROM trips AS t
WHERE t.status = 'Open'
  AND t.available_seats > 0
  AND t.publisher_id <> 2
  AND NOT EXISTS (
      SELECT 1 FROM trip_participants AS tp
      WHERE tp.trip_id = t.id AND tp.user_id = 2 AND tp.status = 'Active'
  )
  AND NOT EXISTS (
      SELECT 1 FROM match_requests AS mr
      WHERE mr.trip_id = t.id AND mr.requester_id = 2
        AND mr.status IN ('Pending', 'Accepted')
  )
ORDER BY t.trip_date, t.start_time;
