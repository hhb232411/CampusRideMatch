-- size=100; query=trip_search; case=q1
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00", "2026-11-20", "6", "17", "18:55", "18:10"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0 AND t.trip_date = ? AND t.origin_area_id = ? AND t.destination_area_id = ? AND t.start_time <= ? AND t.end_time >= ?
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=100; query=trip_search; case=q2
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00", "2026-11-20", "19", "6", "10:50", "09:20"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0 AND t.trip_date = ? AND t.origin_area_id = ? AND t.destination_area_id = ? AND t.start_time <= ? AND t.end_time >= ?
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=100; query=trip_search; case=q3
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00", "2026-11-17", "2", "10", "16:10", "15:10"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0 AND t.trip_date = ? AND t.origin_area_id = ? AND t.destination_area_id = ? AND t.start_time <= ? AND t.end_time >= ?
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=100; query=browse_open; case=all
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=100; query=my_joined_trips; case=q1
-- Bound parameters: [64]
SELECT t.*, tp.status AS participation_status, oa.name AS origin_area,
               da.name AS destination_area, u.display_name AS publisher_name
        FROM trip_participants tp
        JOIN trips t ON t.id = tp.trip_id
        JOIN users u ON u.id = t.publisher_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE tp.user_id = ? ORDER BY t.trip_date DESC, t.start_time;

-- size=100; query=my_joined_trips; case=q2
-- Bound parameters: [15]
SELECT t.*, tp.status AS participation_status, oa.name AS origin_area,
               da.name AS destination_area, u.display_name AS publisher_name
        FROM trip_participants tp
        JOIN trips t ON t.id = tp.trip_id
        JOIN users u ON u.id = t.publisher_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE tp.user_id = ? ORDER BY t.trip_date DESC, t.start_time;

-- size=100; query=my_joined_trips; case=q3
-- Bound parameters: [88]
SELECT t.*, tp.status AS participation_status, oa.name AS origin_area,
               da.name AS destination_area, u.display_name AS publisher_name
        FROM trip_participants tp
        JOIN trips t ON t.id = tp.trip_id
        JOIN users u ON u.id = t.publisher_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE tp.user_id = ? ORDER BY t.trip_date DESC, t.start_time;

-- size=100; query=incoming_requests; case=q1
-- Bound parameters: [31]
SELECT mr.*, t.trip_date, t.start_time, t.end_time,
               u.display_name AS requester_name, oa.name AS origin_area,
               da.name AS destination_area
        FROM match_requests mr
        JOIN trips t ON t.id = mr.trip_id
        JOIN users u ON u.id = mr.requester_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE t.publisher_id = ?
        ORDER BY CASE mr.status WHEN 'Pending' THEN 0 ELSE 1 END, mr.created_at DESC;

-- size=100; query=incoming_requests; case=q2
-- Bound parameters: [45]
SELECT mr.*, t.trip_date, t.start_time, t.end_time,
               u.display_name AS requester_name, oa.name AS origin_area,
               da.name AS destination_area
        FROM match_requests mr
        JOIN trips t ON t.id = mr.trip_id
        JOIN users u ON u.id = mr.requester_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE t.publisher_id = ?
        ORDER BY CASE mr.status WHEN 'Pending' THEN 0 ELSE 1 END, mr.created_at DESC;

-- size=100; query=incoming_requests; case=q3
-- Bound parameters: [85]
SELECT mr.*, t.trip_date, t.start_time, t.end_time,
               u.display_name AS requester_name, oa.name AS origin_area,
               da.name AS destination_area
        FROM match_requests mr
        JOIN trips t ON t.id = mr.trip_id
        JOIN users u ON u.id = mr.requester_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE t.publisher_id = ?
        ORDER BY CASE mr.status WHEN 'Pending' THEN 0 ELSE 1 END, mr.created_at DESC;

-- size=100; query=popular_routes; case=all
-- Bound parameters: []
SELECT oa.name AS origin_area, da.name AS destination_area,
                  COUNT(*) AS trip_count
           FROM trips t
           JOIN location_areas oa ON oa.id = t.origin_area_id
           JOIN location_areas da ON da.id = t.destination_area_id
           GROUP BY t.origin_area_id, t.destination_area_id,
                    oa.name, da.name
           ORDER BY trip_count DESC, oa.name, da.name
           LIMIT 5;

-- size=1000; query=trip_search; case=q1
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00", "2026-12-02", "4", "8", "10:50", "09:20"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0 AND t.trip_date = ? AND t.origin_area_id = ? AND t.destination_area_id = ? AND t.start_time <= ? AND t.end_time >= ?
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=1000; query=trip_search; case=q2
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00", "2026-12-01", "2", "14", "16:00", "15:00"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0 AND t.trip_date = ? AND t.origin_area_id = ? AND t.destination_area_id = ? AND t.start_time <= ? AND t.end_time >= ?
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=1000; query=trip_search; case=q3
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00", "2026-12-08", "5", "2", "16:30", "15:00"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0 AND t.trip_date = ? AND t.origin_area_id = ? AND t.destination_area_id = ? AND t.start_time <= ? AND t.end_time >= ?
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=1000; query=browse_open; case=all
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=1000; query=my_joined_trips; case=q1
-- Bound parameters: [60]
SELECT t.*, tp.status AS participation_status, oa.name AS origin_area,
               da.name AS destination_area, u.display_name AS publisher_name
        FROM trip_participants tp
        JOIN trips t ON t.id = tp.trip_id
        JOIN users u ON u.id = t.publisher_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE tp.user_id = ? ORDER BY t.trip_date DESC, t.start_time;

-- size=1000; query=my_joined_trips; case=q2
-- Bound parameters: [86]
SELECT t.*, tp.status AS participation_status, oa.name AS origin_area,
               da.name AS destination_area, u.display_name AS publisher_name
        FROM trip_participants tp
        JOIN trips t ON t.id = tp.trip_id
        JOIN users u ON u.id = t.publisher_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE tp.user_id = ? ORDER BY t.trip_date DESC, t.start_time;

-- size=1000; query=my_joined_trips; case=q3
-- Bound parameters: [25]
SELECT t.*, tp.status AS participation_status, oa.name AS origin_area,
               da.name AS destination_area, u.display_name AS publisher_name
        FROM trip_participants tp
        JOIN trips t ON t.id = tp.trip_id
        JOIN users u ON u.id = t.publisher_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE tp.user_id = ? ORDER BY t.trip_date DESC, t.start_time;

-- size=1000; query=incoming_requests; case=q1
-- Bound parameters: [92]
SELECT mr.*, t.trip_date, t.start_time, t.end_time,
               u.display_name AS requester_name, oa.name AS origin_area,
               da.name AS destination_area
        FROM match_requests mr
        JOIN trips t ON t.id = mr.trip_id
        JOIN users u ON u.id = mr.requester_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE t.publisher_id = ?
        ORDER BY CASE mr.status WHEN 'Pending' THEN 0 ELSE 1 END, mr.created_at DESC;

-- size=1000; query=incoming_requests; case=q2
-- Bound parameters: [38]
SELECT mr.*, t.trip_date, t.start_time, t.end_time,
               u.display_name AS requester_name, oa.name AS origin_area,
               da.name AS destination_area
        FROM match_requests mr
        JOIN trips t ON t.id = mr.trip_id
        JOIN users u ON u.id = mr.requester_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE t.publisher_id = ?
        ORDER BY CASE mr.status WHEN 'Pending' THEN 0 ELSE 1 END, mr.created_at DESC;

-- size=1000; query=incoming_requests; case=q3
-- Bound parameters: [27]
SELECT mr.*, t.trip_date, t.start_time, t.end_time,
               u.display_name AS requester_name, oa.name AS origin_area,
               da.name AS destination_area
        FROM match_requests mr
        JOIN trips t ON t.id = mr.trip_id
        JOIN users u ON u.id = mr.requester_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE t.publisher_id = ?
        ORDER BY CASE mr.status WHEN 'Pending' THEN 0 ELSE 1 END, mr.created_at DESC;

-- size=1000; query=popular_routes; case=all
-- Bound parameters: []
SELECT oa.name AS origin_area, da.name AS destination_area,
                  COUNT(*) AS trip_count
           FROM trips t
           JOIN location_areas oa ON oa.id = t.origin_area_id
           JOIN location_areas da ON da.id = t.destination_area_id
           GROUP BY t.origin_area_id, t.destination_area_id,
                    oa.name, da.name
           ORDER BY trip_count DESC, oa.name, da.name
           LIMIT 5;

-- size=5000; query=trip_search; case=q1
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00", "2026-12-04", "1", "4", "13:40", "12:10"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0 AND t.trip_date = ? AND t.origin_area_id = ? AND t.destination_area_id = ? AND t.start_time <= ? AND t.end_time >= ?
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=5000; query=trip_search; case=q2
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00", "2026-11-25", "5", "15", "13:40", "12:10"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0 AND t.trip_date = ? AND t.origin_area_id = ? AND t.destination_area_id = ? AND t.start_time <= ? AND t.end_time >= ?
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=5000; query=trip_search; case=q3
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00", "2026-12-01", "4", "17", "09:55", "09:10"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0 AND t.trip_date = ? AND t.origin_area_id = ? AND t.destination_area_id = ? AND t.start_time <= ? AND t.end_time >= ?
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=5000; query=browse_open; case=all
-- Bound parameters: ["2026-11-10", "2026-11-10", "12:00"]
SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE (t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?)) AND t.status = 'Open' AND t.available_seats > 0
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at;

-- size=5000; query=my_joined_trips; case=q1
-- Bound parameters: [88]
SELECT t.*, tp.status AS participation_status, oa.name AS origin_area,
               da.name AS destination_area, u.display_name AS publisher_name
        FROM trip_participants tp
        JOIN trips t ON t.id = tp.trip_id
        JOIN users u ON u.id = t.publisher_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE tp.user_id = ? ORDER BY t.trip_date DESC, t.start_time;

-- size=5000; query=my_joined_trips; case=q2
-- Bound parameters: [31]
SELECT t.*, tp.status AS participation_status, oa.name AS origin_area,
               da.name AS destination_area, u.display_name AS publisher_name
        FROM trip_participants tp
        JOIN trips t ON t.id = tp.trip_id
        JOIN users u ON u.id = t.publisher_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE tp.user_id = ? ORDER BY t.trip_date DESC, t.start_time;

-- size=5000; query=my_joined_trips; case=q3
-- Bound parameters: [70]
SELECT t.*, tp.status AS participation_status, oa.name AS origin_area,
               da.name AS destination_area, u.display_name AS publisher_name
        FROM trip_participants tp
        JOIN trips t ON t.id = tp.trip_id
        JOIN users u ON u.id = t.publisher_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE tp.user_id = ? ORDER BY t.trip_date DESC, t.start_time;

-- size=5000; query=incoming_requests; case=q1
-- Bound parameters: [10]
SELECT mr.*, t.trip_date, t.start_time, t.end_time,
               u.display_name AS requester_name, oa.name AS origin_area,
               da.name AS destination_area
        FROM match_requests mr
        JOIN trips t ON t.id = mr.trip_id
        JOIN users u ON u.id = mr.requester_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE t.publisher_id = ?
        ORDER BY CASE mr.status WHEN 'Pending' THEN 0 ELSE 1 END, mr.created_at DESC;

-- size=5000; query=incoming_requests; case=q2
-- Bound parameters: [5]
SELECT mr.*, t.trip_date, t.start_time, t.end_time,
               u.display_name AS requester_name, oa.name AS origin_area,
               da.name AS destination_area
        FROM match_requests mr
        JOIN trips t ON t.id = mr.trip_id
        JOIN users u ON u.id = mr.requester_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE t.publisher_id = ?
        ORDER BY CASE mr.status WHEN 'Pending' THEN 0 ELSE 1 END, mr.created_at DESC;

-- size=5000; query=incoming_requests; case=q3
-- Bound parameters: [67]
SELECT mr.*, t.trip_date, t.start_time, t.end_time,
               u.display_name AS requester_name, oa.name AS origin_area,
               da.name AS destination_area
        FROM match_requests mr
        JOIN trips t ON t.id = mr.trip_id
        JOIN users u ON u.id = mr.requester_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE t.publisher_id = ?
        ORDER BY CASE mr.status WHEN 'Pending' THEN 0 ELSE 1 END, mr.created_at DESC;

-- size=5000; query=popular_routes; case=all
-- Bound parameters: []
SELECT oa.name AS origin_area, da.name AS destination_area,
                  COUNT(*) AS trip_count
           FROM trips t
           JOIN location_areas oa ON oa.id = t.origin_area_id
           JOIN location_areas da ON da.id = t.destination_area_id
           GROUP BY t.origin_area_id, t.destination_area_id,
                    oa.name, da.name
           ORDER BY trip_count DESC, oa.name, da.name
           LIMIT 5;
