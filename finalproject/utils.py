from contextlib import contextmanager
import mysql.connector
from datetime import timedelta, datetime
import string
import queries

#connection to mysql
@contextmanager
def db_cur():
    flytau_db = None
    cursor = None
    try:
        flytau_db = mysql.connector.connect(
            host = "localhost",
            user = "root",
            password = "nok95nok",
            database = "FLYTAU",
            autocommit = True
        )
        cursor = flytau_db.cursor()
        yield cursor
    except mysql.connector.Error as err:
        raise err
    finally:
        if cursor:
            cursor.close()
        if flytau_db:
            flytau_db.close()


def authenticate(email_or_id: str, password: str):
    """
    check if the user credentials exist, assign the appropriate role to the user (customer / manager)
    :param email_or_id: given user email or worker id
    :param password: given password
    :return: dict including the user's role, email or worker id, and full name
    """

    if email_or_id.isdigit():
        with db_cur() as cursor:
            cursor.execute("SELECT w.f_name_he FROM managers m JOIN workers w ON w.worker_id=m.worker_id WHERE m.worker_id=%s AND m.password=%s",
                           (int(email_or_id), password))
            row = cursor.fetchone()
            if row:
                return {"role": "manager", "identifier": int(email_or_id), "name": row[0]}

    with db_cur() as cursor:
        cursor.execute("SELECT u.f_name FROM customers c JOIN users u ON u.email=c.email WHERE c.email=%s AND c.password=%s",
                       (email_or_id, password))
        row = cursor.fetchone()
        if row:
            return {"role": "customer", "identifier": email_or_id, "name": row[0]}

    return None

def flight_exists(date, origin, destination):
    """
    check if flight exists in the db
    :param date: searched date
    :param origin: searched origin airport
    :param destination: searched destination airport
    :return: flight data if a flight is found, else None
    """
    query = queries.GET_ALL_FLIGHT_DATA
    with db_cur() as cur:
        cur.execute(query, (date, origin, destination, destination, origin))
        return cur.fetchall() or None

def route_exists(origin, destination):
    """
    check if the route exists in the db
    :param origin: searched origin airport
    :param destination: searched destination airport
    :return: 1 if route is found, else None
    """
    if not origin or not destination:
        return False

    query = queries.DOES_ROUTE_EXIST
    with db_cur() as cur:
        cur.execute(query, (origin, destination, destination, origin))
        return cur.fetchone() is not None


def get_available_dates(origin, destination):
    """
    Get the available flight dates, according to the given origin and destination airports.
    :param origin: given origin airport
    :param destination: given destination airport
    :return: list of available dates
    """
    query = queries.GET_AVAILABLE_FLIGHT_DATES
    with db_cur() as cur:
        cur.execute(query, (origin, destination, destination, origin))
        return [row[0].strftime("%Y-%m-%d") for row in cur.fetchall()]


def get_all_airports():
    """
    Get all available airports from mysql(TLV, ETH, etc.)
    :return: list of airports
    """
    query = queries.ALL_AIRPORTS
    with db_cur() as cur:
        cur.execute(query)
        return [row[0] for row in cur.fetchall()]


def build_seat_classes(rows):
    """
    create the seat map for the given seats information (grid)
    :return: dict of seats
    """
    classes = {}

    for class_type, r, c, status, price in rows:
        cls = classes.setdefault(class_type, {
            "price": (float(price) if price is not None else None),
            "cols": set(),
            "grid": {}
        })

        if cls["price"] is None and price is not None:
            cls["price"] = float(price)

        cls["cols"].add(c)
        cls["grid"].setdefault(r, {})[c] = {"status": status}

    for ct in classes:
        classes[ct]["cols"] = sorted(classes[ct]["cols"])
        classes[ct]["rows"] = sorted(classes[ct]["grid"].keys())

    order_pref = {"Business": 0, "Economy": 1}
    return sorted(classes.items(), key=lambda kv: order_pref.get(kv[0], 999))


def _parse_mysql_dt(x):
    """
    MySQL connector usually returns datetime, but if string -> parse
    """
    if isinstance(x, datetime):
        return x
    if isinstance(x, str):
        return datetime.strptime(x, "%Y-%m-%d %H:%M:%S")
    return x

def can_cancel_flight(dep_dt: datetime):
    """
    checks if flight is cancellable by departure time
    :param dep_dt: given departure datetime of flight
    :return: bool
    """
    dep_dt = _parse_mysql_dt(dep_dt)
    return (dep_dt - datetime.now()) >= timedelta(hours=72)


class FlightService:
    """All DB operations related to flights/crew/airplanes go here."""
    @staticmethod
    def get_next_flight_num():
        """
        :return: next flight number in the same format
        """
        with db_cur() as cursor:
            cursor.execute("""
                SELECT COALESCE(MAX(CAST(SUBSTRING(flight_num, 2) AS UNSIGNED)), 0)
                FROM flight
                WHERE flight_num LIKE 'F%'
            """)
            (max_num,) = cursor.fetchone()
            return f"F{int(max_num) + 1}"

    @staticmethod
    def get_flights(selected_status: str = ""):
        """
        filters flights by status if chosen
        :param selected_status: the status chosen by manager
        :return: list of flights
        """
        with db_cur() as cursor:
            if selected_status:
                cursor.execute("""
                    SELECT flight_num, origin_airport, destination_airport,
                           departure_datetime, arrival_datetime, status, airplane_id
                    FROM flight
                    WHERE status = %s
                    ORDER BY departure_datetime;
                """, (selected_status,))
            else:
                cursor.execute("""
                    SELECT flight_num, origin_airport, destination_airport,
                           departure_datetime, arrival_datetime, status, airplane_id
                    FROM flight
                    ORDER BY departure_datetime;
                """)
            return cursor.fetchall()

    @staticmethod
    def get_flight_basic(flight_num: str):
        """
        get the basic information about a specific flight
        :param flight_num: given flight number
        :return: dict of info
        """
        with db_cur() as cursor:
            cursor.execute("""
                SELECT flight_num, origin_airport, destination_airport,
                       departure_datetime, arrival_datetime, status, airplane_id
                FROM flight
                WHERE flight_num=%s
            """, (flight_num,))
            row = cursor.fetchone()
            if not row:
                return None
            fnum, origin, dest, dep_dt, arr_dt, status, airplane_id = row
            return {"flight_num": fnum, "origin": origin,"destination": dest,
                "dep_dt": _parse_mysql_dt(dep_dt),"arr_dt": _parse_mysql_dt(arr_dt),
                "status": status,"airplane_id": airplane_id}

    @staticmethod
    def count_active_orders(flight_num: str):
        """
        count the number of active orders of flight
        :return: num of orders
        """
        with db_cur() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM orders
                WHERE flight_num=%s AND status='active'
            """, (flight_num,))
            return int(cursor.fetchone()[0])

    @staticmethod
    def cancel_flight_and_orders(flight_num: str):
        """
        - Set flight to cancelled + cancel active orders (total_paid=0, cancellation_fee=0)
        - delete order lines of seats from order_seat
        """
        with db_cur() as cursor:
            cursor.execute("""UPDATE orders SET total_paid = 0, cancellation_fee = 0, status = 'system cancellation'
                WHERE flight_num=%s AND (status='active' OR status='Active')
            """, (flight_num,))

            cursor.execute("""UPDATE flight SET status='cancelled' WHERE flight_num=%s""", (flight_num,))

            cursor.execute("""DELETE FROM order_seat WHERE flight_num = %s""",(flight_num,))

    @staticmethod
    def get_route_duration_minutes(origin: str, destination: str):
        """
        :param origin: given origin airport
        :param destination: given destination airport
        :return: duration between airports (minutes)
        """
        with db_cur() as cursor:
            cursor.execute("""
                SELECT duration
                FROM routes
                WHERE (origin_airport=%s AND destination_airport=%s)
                   OR (origin_airport=%s AND destination_airport=%s)
                LIMIT 1
            """, (origin, destination, destination, origin))
            row = cursor.fetchone()
            return int(row[0]) if row else None

    @staticmethod
    def get_free_airplanes(dep_dt: datetime, arr_dt: datetime):
        """
        Airplanes with no overlapping non-cancelled flight.
        If duration > 6 hours -> only Big planes.
        Else -> Big and Small allowed.
        """
        duration_minutes = (arr_dt - dep_dt).total_seconds() / 60
        size_filter_sql = "AND a.plane_size = 'Big'" if duration_minutes > 360 else ""

        with db_cur() as cursor:
            cursor.execute(f"""
                SELECT a.airplane_id, a.plane_size
                FROM airplanes a
                WHERE 1=1
                  {size_filter_sql}
                  AND NOT EXISTS (
                    SELECT 1
                    FROM flight f
                    WHERE f.airplane_id = a.airplane_id
                      AND f.status <> 'cancelled'
                      AND f.departure_datetime < %s
                      AND %s < f.arrival_datetime
                  )
                ORDER BY a.airplane_id;
            """, (arr_dt, dep_dt))
            return cursor.fetchall()

    @staticmethod
    def get_plane_size(airplane_id: int):
        """
        :param airplane_id
        :return: size of airplane
        """
        with db_cur() as cursor:
            cursor.execute("SELECT plane_size FROM airplanes WHERE airplane_id=%s", (airplane_id,))
            row = cursor.fetchone()
            return row[0] if row else None

    @staticmethod
    def crew_needs_for_plane(plane_size: str):
        """
        Returns (need_pilots, need_attendants).
        """
        if plane_size == "Big":
            return 3, 6
        return 2, 3

    @staticmethod
    def get_available_pilots(dep_dt: datetime, arr_dt: datetime, long_flag: int, origin: str):
        """
        get all available pilots according to conditions
        """
        with db_cur() as cursor:
            cursor.execute(queries.AVAILABLE_PILOTS, (dep_dt, long_flag, dep_dt, arr_dt, dep_dt, origin, dep_dt))
            return cursor.fetchall()

    @staticmethod
    def get_available_attendants(dep_dt: datetime, arr_dt: datetime, long_flag: int, origin: str):
        """
        get all available pilots according to conditions
        """
        with db_cur() as cursor:
            cursor.execute(queries.AVAILABLE_ATTENDANTS, (dep_dt, long_flag, dep_dt, arr_dt, dep_dt, origin, dep_dt))
            return cursor.fetchall()

    @staticmethod
    def get_classes_for_airplane(airplane_id: int):
        """
        get the classes of a specific airplane
        """
        with db_cur() as cursor:
            cursor.execute("""
                SELECT class_type
                FROM class
                WHERE airplane_id = %s
                ORDER BY CASE class_type WHEN 'Business' THEN 0 WHEN 'Economy' THEN 1 ELSE 2 END;
            """, (airplane_id,))
            return [r[0] for r in cursor.fetchall()]

    @staticmethod
    def create_flight_with_crew_seats_prices(flight_num: str, origin: str, destination: str, status: str,
        airplane_id: int, dep_dt: datetime, arr_dt: datetime, crew_ids: list[int],
        prices: list[tuple[str, float]]):
        """
        get all the new information about the new flight
        create a new flight and insert into db
        :return: true if flight num is not taken, error if exists
        """
        with db_cur() as cursor:
            cursor.execute("SELECT 1 FROM flight WHERE flight_num=%s", (flight_num,))
            if cursor.fetchone():
                return False, "Flight number already exists."

            cursor.execute("""
                INSERT INTO flight (flight_num, departure_datetime, arrival_datetime, status,
                                    origin_airport, destination_airport, airplane_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (flight_num, dep_dt, arr_dt, status, origin, destination, airplane_id))

            cursor.executemany("""
                INSERT INTO flight_worker (flight_num, worker_id)
                VALUES (%s,%s)
            """, [(flight_num, wid) for wid in crew_ids])

            cursor.execute("""
                INSERT INTO flight_seat (flight_num, airplane_id, class_type, row_num, column_letter, seat_status)
                SELECT %s, %s, sp.class_type, sp.row_num, sp.column_letter, 'available'
                FROM seat_position sp
                WHERE sp.airplane_id = %s
            """, (flight_num, airplane_id, airplane_id))

            cursor.executemany("""
                INSERT INTO flight_class_price (flight_num, airplane_id, class_type, price)
                VALUES (%s, %s, %s, %s)
            """, [(flight_num, airplane_id, ct, pr) for ct, pr in prices])

        return True, None

    @staticmethod
    def get_next_airplane_id():
        """
        Returns MAX(airplane_id)+1 (or 1 if table empty)
        """
        with db_cur() as cursor:
            cursor.execute("""
                SELECT COALESCE(MAX(airplane_id), 0) + 1
                FROM airplanes
            """)
            return int(cursor.fetchone()[0])

    @staticmethod
    def _col_letters(n: int):
        return list(string.ascii_uppercase[:n])

    @staticmethod
    def create_airplane_with_layout(manufacturer: str,date_of_purchase: str,plane_size: str,
        eco_rows: int,eco_cols: int,bus_rows: int | None = None,
        bus_cols: int | None = None):
        """
        Inserts into: airplanes, class, seat_position (all seats)
        Returns the new airplane_id
        """
        ps = (plane_size or "").strip().lower()
        db_plane_size = "Small" if ps == "small" else "Big"
        new_id = FlightService.get_next_airplane_id()

        with db_cur() as cursor:
            cursor.execute("""
                INSERT INTO airplanes (airplane_id, manufacturer, date_of_purchase, plane_size)
                VALUES (%s, %s, %s, %s)
            """, (new_id, manufacturer, date_of_purchase, db_plane_size))

        with db_cur() as cursor:
            cursor.execute("""
                INSERT INTO `class` (airplane_id, class_type, num_rows, num_columns)
                VALUES (%s, %s, %s, %s)
            """, (new_id, "Economy", eco_rows, eco_cols))

        if db_plane_size == "Big":
            if bus_rows is None or bus_cols is None:
                raise ValueError("Missing Business rows/cols for Big plane.")
            with db_cur() as cursor:
                cursor.execute("""
                    INSERT INTO `class` (airplane_id, class_type, num_rows, num_columns)
                    VALUES (%s, %s, %s, %s)
                """, (new_id, "Business", bus_rows, bus_cols))

        seat_rows = []

        for r in range(1, eco_rows + 1):
            for c in FlightService._col_letters(eco_cols):
                seat_rows.append((new_id, "Economy", r, c))

        if db_plane_size == "Big":
            for r in range(1, bus_rows + 1):
                for c in FlightService._col_letters(bus_cols):
                    seat_rows.append((new_id, "Business", r, c))

        with db_cur() as cursor:
            cursor.executemany("""
                INSERT INTO seat_position (airplane_id, class_type, row_num, column_letter)
                VALUES (%s, %s, %s, %s)
            """, seat_rows)

        return new_id

    @staticmethod
    def worker_id_exists(worker_id: int):
        """
        check if id exists
        :return: bool
        """
        with db_cur() as cursor:
            cursor.execute("""
                SELECT 1
                FROM workers
                WHERE worker_id = %s
                LIMIT 1
            """, (worker_id,))
            return cursor.fetchone() is not None

    @staticmethod
    def add_worker_base(worker_id: int,phone_number: str,
        house_num: int,street: str,city: str,
        f_name_he: str,l_name_he: str,work_start_date: str):
        """
        insert to worker all the values
        """
        with db_cur() as cursor:
            cursor.execute("""
                INSERT INTO workers
                    (worker_id, phone_number, house_num, street, city, f_name_he, l_name_he, work_start_date)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (worker_id, phone_number, house_num, street, city, f_name_he, l_name_he, work_start_date))

    @staticmethod
    def add_worker_role(worker_id: int, role: str, lng_flight_approved: int):
        """
        role: 'pilot' / 'flight_attendant'
        lng_flight_approved: 0/1
        """
        lng_flight_approved = 1 if int(lng_flight_approved) == 1 else 0

        if role == "pilot":
            with db_cur() as cursor:
                cursor.execute("""
                    INSERT INTO pilots (worker_id, lng_flight_approved)
                    VALUES (%s, %s)
                """, (worker_id, lng_flight_approved))

        elif role == "flight_attendant":
            with db_cur() as cursor:
                cursor.execute("""
                    INSERT INTO flight_attendants (worker_id, lng_flight_approved)
                    VALUES (%s, %s)
                """, (worker_id, lng_flight_approved))

        else:
            raise ValueError("Invalid role. Expected 'pilot' or 'flight_attendant'.")

    @staticmethod
    def create_worker(worker_id: int,phone_number: str,house_num: int,
        street: str,city: str,f_name_he: str,l_name_he: str,
        work_start_date: str,role: str,lng_flight_approved: int):
        """
          - ensure worker_id is unique
          - insert into workers
          - insert into pilots/flight_attendants
        """
        if FlightService.worker_id_exists(worker_id):
            raise ValueError("WORKER_ID_TAKEN")

        FlightService.add_worker_base(worker_id=worker_id,phone_number=phone_number,
            house_num=house_num,street=street,city=city,f_name_he=f_name_he,
            l_name_he=l_name_he,work_start_date=work_start_date)

        FlightService.add_worker_role(worker_id=worker_id,role=role,
            lng_flight_approved=lng_flight_approved)

    @staticmethod
    def get_flight_statuses():
        """
        all the statuses for flights
        :return: list of statuses
        """
        statuses_lst = ["active","landed","delayed","fully booked","cancelled"]
        return statuses_lst

class UserService:
    @staticmethod
    def customer_exists(email: str):
        """
        check if customer already registered
        :param email: given email for check
        :return: bool
        """
        with db_cur() as cursor:
            cursor.execute("SELECT 1 FROM customers WHERE email=%s", (email,))
            return cursor.fetchone() is not None

    @staticmethod
    def create_customer(email, f_name, l_name, passport_num, birth_date, password, phone1, phone2=None):
        """
        creates new customer in the db, inserts all the values
        - all parameters taken from the "post" form
        """
        with db_cur() as cursor:
            cursor.execute("""INSERT INTO users (email, f_name, l_name) VALUES (%s, %s, %s)""", (email, f_name, l_name))

            cursor.execute("""INSERT INTO customers (email, passport_num, birth_date, password, sign_up_date) VALUES (%s, %s, %s, %s, CURDATE())
            """, (email, passport_num, birth_date, password))

            cursor.execute("""INSERT INTO user_phones (email, phone_num) VALUES (%s, %s)""", (email, phone1))

            if phone2 and phone2 != phone1:
                cursor.execute("""INSERT INTO user_phones (email, phone_num) VALUES (%s, %s)""", (email, phone2))

    @staticmethod
    def is_order_cancellable(order_status, departure_dt):
        """
        check if the order is cancellable:
        - order status must be active
        - flight must be more than 36hrs from now
        :return: true if the order is cancellable, else false
        """
        if not departure_dt:
            return False
        if order_status != "Active":
            return False
        return (departure_dt - datetime.now()) > timedelta(hours=36)

    @staticmethod
    def get_statuses(email):
        """
        get all different order statuses
        :return: list of statuses for given email
        """
        with db_cur() as cursor:
            query = "SELECT DISTINCT orders.status FROM orders WHERE email = %s;"
            cursor.execute(query, (email,))
            return [r[0] for r in cursor.fetchall()]

    @staticmethod
    def enough_seats(selected_flight_num):
        """
        check how many available seats are left
        :return: number of seats
        """
        with db_cur() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM flight_seat fs
                WHERE fs.flight_num = %s
                  AND fs.seat_status = 'available';
            """, (selected_flight_num,))
            return int(cursor.fetchone()[0])





