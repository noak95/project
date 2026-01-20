FLIGHT_STATUS_LANDED = """
UPDATE flight
SET status = 'landed'
WHERE status <> 'cancelled'
  AND arrival_datetime IS NOT NULL
  AND arrival_datetime <= NOW()
"""

FLIGHT_STATUS_FULLY_BOOKED = """
UPDATE flight f
SET f.status = 'fully booked'
WHERE f.status NOT IN ('cancelled','landed')
  AND NOT EXISTS (
      SELECT 1
      FROM flight_seat fs
      WHERE fs.flight_num = f.flight_num
        AND fs.seat_status = 'available'
  );
"""

FLIGHT_STATUS_ACTIVE_FROM_FULLY_BOOKED = """
UPDATE flight f
SET f.status = 'active'
WHERE f.status = 'fully booked'
  AND EXISTS (
      SELECT 1
      FROM flight_seat fs
      WHERE fs.flight_num = f.flight_num
        AND fs.seat_status = 'available'
  );
"""

ALL_AIRPORTS = """
SELECT airport
FROM (
    SELECT origin_airport AS airport FROM routes
    UNION
    SELECT destination_airport AS airport FROM routes
) t
ORDER BY airport;
"""

GET_AVAILABLE_FLIGHT_DATES = """
SELECT DISTINCT DATE(departure_datetime)
FROM flight
WHERE status IN ('active', 'delayed')
  AND departure_datetime > NOW()
  AND (
        (origin_airport = %s AND destination_airport = %s)
     OR (origin_airport = %s AND destination_airport = %s)
  )
ORDER BY DATE(departure_datetime);
"""

GET_ALL_FLIGHT_DATA = """
SELECT *
FROM flight
WHERE status IN ('active','delayed')
  AND DATE(departure_datetime) = %s
  AND (
        (origin_airport = %s AND destination_airport = %s)
     OR (origin_airport = %s AND destination_airport = %s)
  );
"""

DOES_ROUTE_EXIST = """
SELECT 1
FROM routes
WHERE (origin_airport = %s AND destination_airport = %s)
   OR (origin_airport = %s AND destination_airport = %s)
LIMIT 1;
"""

FIND_GUEST_ORDER = """
SELECT
  o.order_id,
  o.order_date,
  o.status AS order_status,
  o.total_paid,
  o.cancellation_fee,
  f.flight_num,
  f.origin_airport,
  f.destination_airport,
  f.departure_datetime,
  f.arrival_datetime,
  f.status AS flight_status,
  COUNT(os.row_num) AS seats_count
FROM orders o
JOIN flight f
  ON f.flight_num = o.flight_num
LEFT JOIN order_seat os
  ON os.order_id = o.order_id
WHERE o.email = %s
  AND o.order_id = %s
GROUP BY
  o.order_id, o.order_date, o.status, o.total_paid, o.cancellation_fee,
  f.flight_num, f.origin_airport, f.destination_airport,
  f.departure_datetime, f.arrival_datetime, f.status
"""

FIND_CUSTOMER_ORDERS = """
SELECT
  o.order_id,
  o.order_date,
  o.status AS order_status,
  o.total_paid,
  o.cancellation_fee,
  f.flight_num,
  f.origin_airport,
  f.destination_airport,
  f.departure_datetime,
  f.arrival_datetime,
  f.status AS flight_status,
  COUNT(os.row_num) AS seats_count
FROM orders o
JOIN flight f
  ON f.flight_num = o.flight_num
LEFT JOIN order_seat os
  ON os.order_id = o.order_id
WHERE o.email = %s
"""

ORDER_DETAILS = """
SELECT o.order_id, o.order_date, o.status,
     o.total_paid, o.cancellation_fee,
     f.flight_num, f.origin_airport, f.destination_airport,
     f.departure_datetime, f.arrival_datetime
FROM orders o
JOIN flight f ON f.flight_num = o.flight_num
WHERE o.order_id=%s AND o.email=%s
LIMIT 1
"""

RELEASE_SEATS_OF_ORDER = """
UPDATE flight_seat fs
JOIN order_seat os
  ON os.flight_num = fs.flight_num
 AND os.airplane_id = fs.airplane_id
 AND os.class_type = fs.class_type
 AND os.row_num = fs.row_num
 AND os.column_letter = fs.column_letter
SET fs.seat_status = 'available'
WHERE os.order_id = %s
  AND fs.flight_num = %s
"""

CANCELLATION_RATE_BY_MONTH = """
SELECT DATE_FORMAT(order_date, '%Y-%m') AS month,
    ROUND(100 * SUM(CASE WHEN status = 'customer cancellation' THEN 1 ELSE 0 END) / COUNT(*), 2) 
        AS cancellation_rate_percent
FROM orders
WHERE order_date IS NOT NULL
GROUP BY DATE_FORMAT(order_date, '%Y-%m')
ORDER BY month;
"""

MONTHLY_ACTIVITY_SUMMARY_PER_AIRCRAFT = """
WITH flight_base AS (
SELECT
    f.airplane_id,
    DATE_FORMAT(f.departure_datetime, '%Y-%m') AS ym,
    DATE(f.departure_datetime) AS flight_date,
    f.status,
    f.origin_airport,
    f.destination_airport,
    TIMESTAMPDIFF(MINUTE, f.departure_datetime, f.arrival_datetime) AS dur_min
FROM flight f
),
route_rank AS (
SELECT
    airplane_id,
    ym,
    origin_airport,
    destination_airport,
    COUNT(*) AS route_cnt,
    ROW_NUMBER() OVER (
        PARTITION BY airplane_id, ym
        ORDER BY COUNT(*) DESC, origin_airport, destination_airport
    ) AS rn
FROM flight_base
GROUP BY airplane_id, ym, origin_airport, destination_airport
),
monthly AS (
SELECT
    airplane_id,
    ym,
    SUM(CASE WHEN status <> 'cancelled' THEN 1 ELSE 0 END) AS flights_done,
    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS flights_cancelled,
    COUNT(DISTINCT CASE WHEN status <> 'cancelled' THEN flight_date END) AS active_days
FROM flight_base
GROUP BY airplane_id, ym
)
SELECT
m.airplane_id,
m.ym AS month,
m.flights_done,
m.flights_cancelled,
ROUND(100 * m.active_days / 30, 2) AS utilization_percent,
CONCAT(r.origin_airport, '-', r.destination_airport) AS dominant_route
FROM monthly m
LEFT JOIN route_rank r
ON r.airplane_id = m.airplane_id
AND r.ym = m.ym
AND r.rn = 1
ORDER BY m.airplane_id, m.ym
"""

REVENUE_BY_PLANE_INFO = """
SELECT A.manufacturer, A.plane_size, C.class_type, 
       COALESCE(SUM(OS.price_at_purchase), 0) AS income
FROM airplanes A
CROSS JOIN (
    SELECT 'Economy' AS class_type 
    UNION ALL 
    SELECT 'Business' AS class_type
) C
LEFT JOIN order_seat OS 
    ON OS.airplane_id = A.airplane_id 
    AND OS.class_type = C.class_type
WHERE NOT (A.plane_size = 'Small' AND C.class_type = 'Business')
GROUP BY A.manufacturer, A.plane_size, C.class_type
ORDER BY A.manufacturer, A.plane_size, C.class_type
"""

AVAILABLE_PILOTS = """
SELECT p.worker_id, w.f_name_he, w.l_name_he
FROM pilots p
JOIN workers w ON w.worker_id = p.worker_id

LEFT JOIN (
    SELECT fw.worker_id,
           MAX(f.arrival_datetime) AS last_arrival,
           SUBSTRING_INDEX(
               GROUP_CONCAT(f.destination_airport ORDER BY f.arrival_datetime DESC),
               ',', 1
           ) AS last_dest
    FROM flight_worker fw
    JOIN flight f ON f.flight_num = fw.flight_num
    WHERE f.status <> 'cancelled'
      AND f.arrival_datetime < %s
    GROUP BY fw.worker_id
) lastf ON lastf.worker_id = p.worker_id

WHERE (%s = 0 OR p.lng_flight_approved = 1)
AND DATE(%s) >= DATE(w.work_start_date)

  AND NOT EXISTS (
      SELECT 1
      FROM flight_worker fw2
      JOIN flight f2 ON f2.flight_num = fw2.flight_num
      WHERE fw2.worker_id = p.worker_id
        AND f2.status <> 'cancelled'
        AND f2.departure_datetime < %s
        AND %s < f2.arrival_datetime
  )

  AND (
        lastf.last_arrival IS NULL
     OR lastf.last_dest = %s
     OR DATE(%s) >= DATE(lastf.last_arrival) + INTERVAL 1 DAY
  )

ORDER BY p.worker_id;
"""

AVAILABLE_ATTENDANTS = """
SELECT fa.worker_id, w.f_name_he, w.l_name_he
FROM flight_attendants fa
JOIN workers w ON w.worker_id = fa.worker_id

LEFT JOIN (
    SELECT fw.worker_id,
           MAX(f.arrival_datetime) AS last_arrival,
           SUBSTRING_INDEX(
               GROUP_CONCAT(f.destination_airport ORDER BY f.arrival_datetime DESC),
               ',', 1
           ) AS last_dest
    FROM flight_worker fw
    JOIN flight f ON f.flight_num = fw.flight_num
    WHERE f.status <> 'cancelled'
      AND f.arrival_datetime < %s
    GROUP BY fw.worker_id
) lastf ON lastf.worker_id = fa.worker_id

WHERE (%s = 0 OR fa.lng_flight_approved = 1)
AND DATE(%s) >= DATE(w.work_start_date)

  AND NOT EXISTS (
      SELECT 1
      FROM flight_worker fw2
      JOIN flight f2 ON f2.flight_num = fw2.flight_num
      WHERE fw2.worker_id = fa.worker_id
        AND f2.status <> 'cancelled'
        AND f2.departure_datetime < %s
        AND %s < f2.arrival_datetime
  )

  AND (
        lastf.last_arrival IS NULL
     OR lastf.last_dest = %s
     OR DATE(%s) >= DATE(lastf.last_arrival) + INTERVAL 1 DAY
  )

ORDER BY fa.worker_id;
"""

SEAT_MAP = """
SELECT
    sp.class_type,
    sp.row_num,
    sp.column_letter,
    CASE
      WHEN os.flight_num IS NOT NULL AND o.status = "Active" THEN 'TAKEN'
      WHEN fs.seat_status = 'available' THEN 'AVAILABLE'
      ELSE 'TAKEN'
    END AS final_status,
    fcp.price
FROM flight f
JOIN seat_position sp
  ON sp.airplane_id = f.airplane_id

LEFT JOIN flight_seat fs
  ON fs.flight_num = f.flight_num
 AND fs.airplane_id = sp.airplane_id
 AND fs.class_type = sp.class_type
 AND fs.row_num = sp.row_num
 AND fs.column_letter = sp.column_letter

LEFT JOIN order_seat os
  ON os.flight_num = f.flight_num
 AND os.airplane_id = sp.airplane_id
 AND os.class_type = sp.class_type
 AND os.row_num = sp.row_num
 AND os.column_letter = sp.column_letter

LEFT JOIN orders o
  ON os.order_id = o.order_id

LEFT JOIN flight_class_price fcp
  ON fcp.flight_num  = f.flight_num
 AND fcp.airplane_id = f.airplane_id
 AND fcp.class_type  = sp.class_type

WHERE f.flight_num = %s
ORDER BY
  CASE sp.class_type WHEN 'Business' THEN 0 WHEN 'Economy' THEN 1 ELSE 2 END,
  sp.row_num, sp.column_letter;
"""

INSERT_GUEST_INTO_USERS = """
INSERT INTO users (email, f_name, l_name)
VALUES (%s, %s, %s)
ON DUPLICATE KEY UPDATE
  f_name = VALUES(f_name),
  l_name = VALUES(l_name)
"""

INSERT_TO_ORDERS = """
INSERT INTO orders (email, flight_num, order_date, status, total_paid, cancellation_fee)
VALUES (%s, %s, %s, 'Active', %s, %s)
"""

INSERT_INTO_ORDER_SEAT = """
INSERT INTO order_seat
  (order_id, flight_num, airplane_id, class_type, row_num, column_letter, price_at_purchase)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

CHECK_AVAILABLE_SEATS = """
SELECT COUNT(*)
FROM flight_seat
WHERE flight_num = %s AND seat_status = 'available'
"""

ORDER_SEATS = """
SELECT class_type, row_num, column_letter, price_at_purchase
FROM order_seat
WHERE order_id = %s
ORDER BY class_type, row_num, column_letter
"""

USER_DETAILS = """
SELECT u.f_name, u.l_name, c.birth_date, c.passport_num
FROM users u
LEFT JOIN customers c ON c.email = u.email
WHERE u.email = %s
"""

FLIGHTS_TO_LAND = """
SELECT flight_num
FROM flight
WHERE status <> 'cancelled'
  AND arrival_datetime IS NOT NULL
  AND arrival_datetime <= NOW()
  AND status <> 'landed'
"""

CHANGE_ORDER_STATUS_AFTER_LANDING= """
UPDATE orders SET status = 'completed' WHERE flight_num = %s """