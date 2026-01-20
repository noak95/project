import os
from flask import Flask, request, redirect, render_template, url_for, session, flash
from flask_session import Session
from datetime import timedelta, datetime, date
import mysql.connector
from utils import build_seat_classes, authenticate,route_exists, flight_exists, db_cur, can_cancel_flight, _parse_mysql_dt, FlightService, UserService, get_available_dates, get_all_airports
from functools import wraps
from reports import report_revenue, report_operational,report_cancellation
import queries
import time

#initialize app
app = Flask(__name__)

#initialize session
app.secret_key = "6f9e3b7d1a4c8e2f5d0c9b7a1e4f6d8c2b9a5e0f7c1d3a8b4e6f2c9d1a0b"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(BASE_DIR, "flask_session_data")
os.makedirs(SESSION_DIR, exist_ok=True)
app.config.update(
    SESSION_TYPE = "filesystem",
    SESSION_FILE_DIR = SESSION_DIR,
    SESSION_PERMANENT = True,
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=15),
    SESSION_REFRESH_EACH_REQUEST = True,
    SESSION_COOKIE_SECURE = False
)
Session(app)

def manager_only(fn):
    """
    decorator to check whether the user is a manager
    :param fn: wrapper function
    :return: wrapper if user is a manager, else redirect to login page
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "manager":
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def not_manager(fn):
    """
    decorator to check whether the user is a customer
    :param fn: wrapper function
    :return: redirect to home page if the user is manager, else return the wrapper
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") == "manager":
            return redirect(url_for("home"))
        return fn(*args, **kwargs)
    return wrapper


_last_maint_run = 0

@app.before_request
def auto_land_flights():
    """
    change flight status to 'landed' if a flight has landed,
    change flight status to 'fully booked' if there are no seats available,
    change flight status back to 'active' from 'fully booked' if seats have been freed.
    Maintenance: update flight statuses.
    Runs rarely and never blocks the page if DB/query fails.
    """
    global _last_maint_run

    if request.path.startswith("/static"):
        return None

    now = time.time()
    if now - _last_maint_run < 15:
        return None
    _last_maint_run = now

    try:
        with db_cur() as cursor:
            cursor.execute(queries.FLIGHTS_TO_LAND)
            flights_landed = [row[0] for row in cursor.fetchall()]
            cursor.execute(queries.FLIGHT_STATUS_LANDED)
            for fn in flights_landed:
                cursor.execute(queries.CHANGE_ORDER_STATUS_AFTER_LANDING, (fn,))
            cursor.execute(queries.FLIGHT_STATUS_FULLY_BOOKED)
            cursor.execute(queries.FLIGHT_STATUS_ACTIVE_FROM_FULLY_BOOKED)
    except Exception as e:
        print("auto_land_flights FAILED:", repr(e))
        return None

    return None

@app.before_request
def auto_land_flights():
    """

    """
    try:
        with db_cur() as cursor:
            cursor.execute(queries.FLIGHT_STATUS_LANDED)
            cursor.execute(queries.FLIGHT_STATUS_FULLY_BOOKED)
            cursor.execute(queries.FLIGHT_STATUS_ACTIVE_FROM_FULLY_BOOKED)
    except Exception as e:
        print("auto_land_flights error:", e)
        return None

@app.route('/', methods=['GET', 'POST'])
def home():
    """
    app route for the flight search page:
    - display a different page according to the session role.
    - check if the searched origin and destination airports route exist
    - get flight data for the selected route and date
    - redirect to the order page
    """
    airports = get_all_airports()
    if request.method == "GET":
        if session.get("role") == "manager":
            return render_template(
                "search_flights.html",
                airports=airports,
                origin=None,
                destination=None,
                passengers=1,
                error="Managers can not book flights"
            )
        else:
            return render_template(
                "search_flights.html",
                airports=airports,
                origin=None,
                destination=None,
                passengers=1,
                error=None
            )

    error = None
    origin = request.form.get("origin") or None
    destination = request.form.get("destination") or None
    passengers = int(request.form.get("passengers", 1))
    selected_date = request.form.get("date") or None

    available_dates = []

    if origin and destination:
        if not route_exists(origin, destination):
            error = "No route exists between the selected airports."
        else:
            available_dates = get_available_dates(origin, destination)

    if selected_date and origin and destination and not error:
        if available_dates and selected_date not in available_dates:
            error = "No flights available on this date for the selected route."
        else:
            data = flight_exists(selected_date, origin, destination)
            if data:
                return render_template(
                    "order.html",
                    options=data,
                    date=selected_date,
                    origin=origin,
                    destination=destination,
                    passengers=passengers
                )
            else:
                error = "No active flights found for the selected date."

    return render_template(
        "search_flights.html",
        airports=airports,
        origin=origin,
        destination=destination,
        passengers=passengers,
        error=error
    )

@app.route('/order', methods=['POST', 'GET'])
@not_manager
def order_page():
    """
    app route for user order page
    - get selected flight num and check availability of seats
    redirect to seats page if there are enough seats
    """
    passengers = int(request.args.get("passengers", 1))

    if request.method == 'POST':
        selected_flight_num = request.form.get("flight_num")
        available = UserService.enough_seats(selected_flight_num)
        if available < passengers:
            error = f"Not enough available seats for this flight. {available} seats left."
            return render_template('order.html', passengers=passengers, error=error)

        return redirect(url_for('seats_page', flight_num=selected_flight_num, passengers=passengers))
    return render_template('order.html', passengers=passengers)

@app.route('/flights/<flight_num>/seats', methods=['GET', 'POST'])
@not_manager
def seats_page(flight_num):
    """
    app route for the seats page
    - gets information about the flight seats
    - creates a grid for the seats
    - checks if enough seats selected by user
    redirect to order summary page
    """
    passengers = int(request.args.get("passengers", 1))
    with db_cur() as cursor:
        cursor.execute(queries.SEAT_MAP,(flight_num,))
        rows = cursor.fetchall()

    sorted_classes = build_seat_classes(rows)
    if request.method == "POST":
        selected = request.form.getlist("seats")
        if len(selected) != passengers:
            error = f"You must choose exactly {passengers} seats. You selected {len(selected)}."
            return render_template(
                "seats.html",
                flight_num=flight_num,
                classes=sorted_classes,
                passengers=passengers,
                error=error
            )
        return redirect(url_for("order_summary", flight_num=flight_num, selected_seats=selected))

    return render_template("seats.html", flight_num=flight_num, classes=sorted_classes, passengers=passengers)


@app.route('/order_summary', methods=['GET', 'POST'])
def order_summary():
    """
    app route for the order summary page
    - shows order summary with the flight and seats chosen
    - for customer: information is already saved in db
    - for guest: fill the details and insert into db
    if all went well - redirect to final summary page
    """
    if request.method == "GET":
        flight_num = (request.args.get("flight_num") or "").strip()
        selected_seats = request.args.getlist("selected_seats")
        if not selected_seats:
            seats_str = (request.args.get("selected_seats") or "").strip()
            if seats_str:
                selected_seats = [s.strip() for s in seats_str.split(",") if s.strip()]

        tmpl = "order_summary_customer.html" if session.get("role") == "customer" else "order_summary_guest.html"

        if not flight_num or not selected_seats:
            return render_template(
                tmpl,
                flight_num=flight_num,
                selected_seats=selected_seats,
                error="Missing flight number or selected seats."
            )

        return render_template(tmpl, flight_num=flight_num, selected_seats=selected_seats)

    flight_num = (request.form.get("flight_num") or "").strip()
    selected_seats_raw = request.form.getlist("selected_seats")

    if not selected_seats_raw:
        seats_str = (request.form.get("selected_seats") or "").strip()
        if seats_str:
            selected_seats_raw = [s.strip() for s in seats_str.split(",") if s.strip()]

    role = session.get("role")
    tmpl = "order_summary_customer.html" if role == "customer" else "order_summary_guest.html"

    if not flight_num or not selected_seats_raw:
        return render_template(tmpl, flight_num=flight_num, selected_seats=selected_seats_raw,
                               error="Missing flight number or selected seats.")

    guest_payload = None
    if role == "customer":
        email = (session.get("email") or "").strip()
        if not email:
            return render_template("order_summary_customer.html",
                                   flight_num=flight_num, selected_seats=selected_seats_raw,
                                   error="You must be logged in.")
    else:
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        email = (request.form.get("email") or "").strip()
        phone_num = (request.form.get("phone_num") or "").strip()

        if not all([first_name, last_name, email, phone_num]):
            return render_template("order_summary_guest.html",
                                   flight_num=flight_num, selected_seats=selected_seats_raw,
                                   error="Please fill in all guest details.",
                                   first_name=first_name, last_name=last_name,
                                   email=email, phone_num=phone_num)

        guest_payload = {"first_name": first_name, "last_name": last_name, "phone_num": phone_num}

    try:
        parsed = []
        for s in selected_seats_raw:
            parts = s.split("|")
            if len(parts) != 3:
                raise ValueError(s)
            ct = parts[0].strip()
            rn = int(parts[1])
            cl = parts[2].strip()
            parsed.append((ct, rn, cl))
    except Exception:
        return render_template(tmpl, flight_num=flight_num, selected_seats=selected_seats_raw,
                               error="Problematic seats choice.")

    try:
        with db_cur() as cursor:
            if role != "customer":
                cursor.execute(queries.INSERT_GUEST_INTO_USERS,(email, guest_payload["first_name"], guest_payload["last_name"]))
                cursor.execute("""
                    INSERT IGNORE INTO user_phones (email, phone_num)
                    VALUES (%s, %s)
                """, (email, guest_payload["phone_num"]))

            seat_where = " OR ".join(["(row_num=%s AND column_letter=%s)"] * len(parsed))
            params = [flight_num]
            for ct, rn, cl in parsed:
                params.extend([rn, cl])

            cursor.execute(f"""
                SELECT airplane_id, class_type, row_num, column_letter, seat_status
                FROM flight_seat
                WHERE flight_num = %s AND ({seat_where})
            """, tuple(params))

            rows = cursor.fetchall()

            if len(rows) != len(parsed):
                raise Exception("One or more seats do not exist for this flight.")

            not_available = [x for x in rows if (x[4] or "").lower() != "available"]
            if not_available:
                bad = [f"{x[2]}{x[3]}({x[4]})" for x in not_available]
                raise Exception("Some seats are no longer available: " + ", ".join(bad))

            airplane_id = rows[0][0]

            cursor.execute("""
                SELECT class_type, price
                FROM flight_class_price
                WHERE flight_num = %s
            """, (flight_num,))
            price_rows = cursor.fetchall()
            price_map = {ct: float(p) for (ct, p) in price_rows}

            seat_inserts = []
            total_paid = 0.0

            for (airplane_id_db, class_type_db, row_num_db, col_db, status_db) in rows:
                if class_type_db not in price_map:
                    raise Exception(f"Missing price for class '{class_type_db}'.")

                pr = price_map[class_type_db]
                total_paid += pr
                seat_inserts.append((class_type_db, row_num_db, col_db, pr))

            cursor.execute(queries.INSERT_TO_ORDERS, (email, flight_num, date.today(), total_paid, total_paid * 0.05))

            order_id = cursor.lastrowid

            cursor.executemany(queries.INSERT_INTO_ORDER_SEAT, [(order_id, flight_num, airplane_id, ct, rn, cl, pr) for (ct, rn, cl, pr) in seat_inserts])

            cursor.execute(f"""
                UPDATE flight_seat
                SET seat_status = 'taken'
                WHERE flight_num = %s AND ({seat_where})
            """, tuple(params))

            cursor.execute(queries.CHECK_AVAILABLE_SEATS, (flight_num,))
            remaining = cursor.fetchone()[0]

            if remaining == 0:
                cursor.execute("""
                    UPDATE flight
                    SET status = 'fully booked'
                    WHERE flight_num = %s
                """, (flight_num,))

            return redirect(url_for("final_summary", order_id=order_id))

    except Exception as e:
        return render_template(tmpl, flight_num=flight_num, selected_seats=selected_seats_raw, error=str(e))


@app.route("/final_summary", methods=["GET"])
def final_summary():
    """
    app route for the final summary page
    - gets all the order information and user information
    - shows final summary of all date
    """
    order_id = request.args.get("order_id", type=int)
    if not order_id:
        return render_template(
            "final_summary.html",
            order=None,
            seats=None,
            person=None,
            error="Missing order_id."
        )

    with db_cur() as cursor:
        cursor.execute("""
            SELECT o.order_id, o.email, o.flight_num, o.order_date, o.status, o.total_paid
            FROM orders o
            WHERE o.order_id = %s
        """, (order_id,))
        order = cursor.fetchone()

        if not order:
            return render_template(
                "final_summary.html",
                order=None,
                seats=None,
                person=None,
                error="Order not found."
            )

        email = order[1]

        cursor.execute(queries.ORDER_SEATS,(order_id,))
        seats = cursor.fetchall()

        cursor.execute(queries.USER_DETAILS,(email,))
        person = cursor.fetchone()

    return render_template(
        "final_summary.html",
        order=order,
        seats=seats,
        person=person
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    app route for the login page:
    - make sure the user has filled in all fields
    - check the given credentials are valid
    - get the customer / manager information and enter it into the session
    - redirect to home page
    """
    if request.method == 'GET':
        return render_template('login.html')

    email_or_id = request.form.get("email")
    password = request.form.get("password")
    login_type = request.form.get("login_type")

    if not email_or_id or not password or not login_type:
        return render_template(
            'login.html',
            error="Please fill in all fields."
        )

    auth = authenticate(email_or_id, password)

    if not auth or auth["role"] != login_type:
        return render_template(
            'login.html',
            error="Wrong credentials or wrong login type."
        )

    else:
        session.clear()

        session["logged_in"] = True
        session["role"] = auth["role"]
        session["username"] = auth["name"]

        if auth["role"] == "manager":
            session["worker_id"] = auth["identifier"]
        else:
            session["email"] = auth["identifier"]

        return redirect(url_for('home'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """
    app route for the sign-up page
    - checks if customer already registered
    - if not, creates a new account for them
    - after success, redirects to log in page
    """
    if request.method == 'GET':
        return render_template('signup.html')

    f_name = (request.form.get('f_name_eng') or '').strip()
    l_name = (request.form.get('l_name_eng') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    phone1 = (request.form.get('phone1') or '').strip()
    phone2 = (request.form.get('phone2') or '').strip() or None
    passport_num = (request.form.get('passport_num') or '').strip()
    birth_date = (request.form.get('birth_date') or '').strip()
    password = (request.form.get('password') or '').strip()

    if not all([f_name, l_name, email, phone1, passport_num, birth_date, password]):
        return render_template('signup.html', error="Please fill in all required fields.")

    try:
        if UserService.customer_exists(email):
            return render_template('signup.html', error="This email is already registered.")

        UserService.create_customer(
            email=email, f_name=f_name, l_name=l_name,
            passport_num=passport_num, birth_date=birth_date, password=password,
            phone1=phone1, phone2=phone2
        )
        return redirect(url_for('login'))

    except mysql.connector.Error as err:
        return render_template('signup.html', error=f"Database error: {err}")


@app.route('/logout')
def logout():
    """
    app route for the logout function
    - log out of the account, clear the session
    - redirects to home page
    """
    session.clear()
    return redirect(url_for('home'))

@app.route('/find_order', methods=['GET', 'POST'])
def find_order():
    """
    app route for the order search page:
    - get the searched email and order id
    - check if the given email and order id are valid
    - get the order data according to the email and order id
    """
    rows = []
    error = None
    email = ""
    order_id = ""
    can_cancel = {}

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        order_id = (request.form.get("order_id") or "").strip()

        if not email or not order_id:
            error = "Please fill in both Email and Order ID."
        elif not order_id.isdigit():
            error = "Order ID must be a number."
        else:
            query = queries.FIND_GUEST_ORDER

            with db_cur() as cursor:
                cursor.execute(query, (email, int(order_id)))
                rows = cursor.fetchall()

            if not rows:
                error = "No matching order found."
            else:
                for r in rows:
                    oid = r[0]
                    order_status = r[2]
                    departure_dt = r[8]
                    can_cancel[oid] = UserService.is_order_cancellable(order_status, departure_dt)

    return render_template("find_order.html", rows=rows, error=error,
                           email=email, order_id=order_id, can_cancel=can_cancel)


@app.route('/my_orders', methods=['GET'])
@not_manager
def my_orders():
    """
    app route for the order history page:
    - get the user email from the current session
    - get the given filtered status
    - get the customer's order history
    """
    email = session.get("email")
    if not email:
        return redirect(url_for("login"))

    selected_status = (request.args.get("status", "") or "").strip()

    query = queries.FIND_CUSTOMER_ORDERS

    params = [email]

    if selected_status:
        query += " AND o.status = %s "
        params.append(selected_status)

    query += '''
        GROUP BY
          o.order_id, o.order_date, o.status, o.total_paid, o.cancellation_fee,
          f.flight_num, f.origin_airport, f.destination_airport,
          f.departure_datetime, f.arrival_datetime, f.status
        ORDER BY o.order_date DESC;
    '''

    with db_cur() as cursor:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

    can_cancel = {}
    for r in rows:
        oid = r[0]
        order_status = r[2]
        departure_dt = r[8]
        can_cancel[oid] = UserService.is_order_cancellable(order_status, departure_dt)

    statuses = UserService.get_statuses(email)

    return render_template(
        "my_orders.html",
        rows=rows,
        statuses=statuses,
        selected_status=selected_status,
        can_cancel=can_cancel,
        email=email
    )

@app.route('/orders/<int:order_id>/cancel', methods=['GET','POST'])
def cancel_order_confirm(order_id):
    """
    app route for the order cancellation confirm page:
    - get the order number and email of user
    - fetch the info about the specific order
    - cancel the order - release the seats taken, and return to home/my_orders
    :param order_id: chosen order number from my_orders or find_order
    """
    if session.get("email"):
        redirect_to = "my_orders"
        email = session.get("email")
    else:
        redirect_to = "home"
        email = request.args.get("email")

    if request.method == "GET":

        with db_cur() as cursor:
            cursor.execute(queries.ORDER_DETAILS, (order_id, email))
            row = cursor.fetchone()
            cursor.fetchall()

        return render_template("cancel_order_confirm.html", row=row, guest_email=email, redirect_to=redirect_to)

    with db_cur() as cursor:
        cursor.execute("SELECT f.flight_num FROM orders o JOIN flight f ON f.flight_num = o.flight_num WHERE o.order_id=%s AND o.email=%s LIMIT 1", (order_id, email))
        flight_num = cursor.fetchone()[0]
        cursor.execute("UPDATE orders SET status = %s, total_paid = cancellation_fee, cancellation_fee = 0 WHERE order_id = %s AND email = %s;",
            ("customer cancellation", order_id, email))
        cursor.execute(queries.RELEASE_SEATS_OF_ORDER, (order_id, flight_num))
        cursor.execute("DELETE FROM order_seat WHERE order_id = %s;", (order_id,))

    if redirect_to == "my_orders":
        return redirect(url_for("my_orders"))
    return redirect(url_for("home"))


@app.route('/revenue_report', methods=['GET'])
@manager_only
def revenue_report():
    """
    app route for the revenue report page
    """
    r = report_revenue()
    return render_template("revenue_report.html", data=r[0],total_revenue=r[1],labels=r[2],
                           economy_data=r[3],business_data=r[4])

@app.route('/operational_report', methods=['GET'])
@manager_only
def operational_report():
    """
    app route for the operational report page
    """
    o = report_operational()
    return render_template("operational_report.html",aircraft_data=o[0],avg_utilization=o[1],total_aircraft=o[2],
                           all_months=o[3],chart_datasets=o[4])

@app.route('/cancellation_report', methods=['GET'])
@manager_only
def cancellation_report():
    """
    app route for the cancellation report page
    """
    c = report_cancellation()
    return render_template("cancellation_report.html", avg_rate=c[0],max_rate=c[1],min_rate=c[2],months_json=c[3],rates_json=c[4],results=c[5])


@app.route('/manager', methods=['GET'])
@manager_only
def manager_home():
    """
    app route for the manager dashboard page
    - can filter flights by status
    - shows a cancel option if cancellable
    """
    selected_status = (request.args.get("status", "") or "").strip()

    statuses = FlightService.get_flight_statuses()
    flights = FlightService.get_flights(selected_status)

    can_cancel = {}
    for f in flights:
        flight_num = f[0]
        dep_dt = _parse_mysql_dt(f[3])
        can_cancel[flight_num] = can_cancel_flight(dep_dt)

    return render_template(
        "manager_home.html",
        statuses=statuses,
        selected_status=selected_status,
        flights=flights,
        can_cancel=can_cancel
    )

@app.route('/manager/flights/<flight_num>/status', methods=['POST'])
@manager_only
def update_flight_status(flight_num):
    """
    an extension for the manager dashboard page to update flights statuses
    :param flight_num: specific flight number to update
    :return: updated page
    """
    new_status = (request.form.get("status") or "").strip()
    if not new_status:
        return redirect(url_for("manager_home"))

    allowed = set(FlightService.get_flight_statuses())
    if new_status not in allowed:
        return redirect(url_for("manager_home"))

    with db_cur() as cursor:
        cursor.execute("UPDATE flight SET status = %s WHERE flight_num = %s",(new_status, flight_num))

    return redirect(url_for("manager_home", status=request.args.get("status", "")))

@app.route('/manager/flights/<flight_num>/cancel', methods=['GET','POST'])
@manager_only
def cancel_flight_confirm(flight_num):
    if request.method == 'GET':
        info = FlightService.get_flight_basic(flight_num)
        if not info:
            return redirect(url_for("manager_home"))

        allowed = (info["status"] != "cancelled") and can_cancel_flight(info["dep_dt"])
        dep_str = info["dep_dt"].strftime("%Y-%m-%d %H:%M:%S")
        active_orders_count = FlightService.count_active_orders(flight_num)

        if not allowed:
            return render_template(
                "manager_cancel_flight.html",
                error="Cancellation is not allowed (already cancelled or less than 72 hours before departure).",
                flight_num=info["flight_num"],
                origin=info["origin"],
                destination=info["destination"],
                departure=dep_str,
                status=info["status"],
                active_orders_count=active_orders_count
            )

        return render_template(
            "manager_cancel_flight.html",
            flight_num=info["flight_num"],
            origin=info["origin"],
            destination=info["destination"],
            departure=dep_str,
            status=info["status"],
            active_orders_count=active_orders_count
        )

    info = FlightService.get_flight_basic(flight_num)
    if not info:
        return redirect(url_for("manager_home"))

    allowed = (info["status"] != "cancelled") and can_cancel_flight(info["dep_dt"])
    if not allowed:
        return redirect(url_for("manager_home"))
    print(flight_num)
    FlightService.cancel_flight_and_orders(flight_num)
    return redirect(url_for("manager_home"))

@app.route("/manager/add_flight", methods=["GET", "POST"])
@manager_only
def add_flight():
    """
    app route for the add new flight page for manager
    - generates the next flight number
    - checks for available airplanes by time and size
    - redirects to choose aircraft
    """
    if request.method == 'GET':
        flight_num = FlightService.get_next_flight_num()
        return render_template("add_flight.html", flight_num=flight_num, error=None)

    origin = (request.form.get("origin") or "").strip().upper()
    destination = (request.form.get("destination") or "").strip().upper()
    status = (request.form.get("status") or "active").strip().lower()
    flight_num = FlightService.get_next_flight_num()
    dep_raw = request.form.get("departure_datetime")
    if not dep_raw:
        return render_template("add_flight.html",flight_num=flight_num, error="Departure datetime is required.")

    dep_dt = datetime.strptime(dep_raw, "%Y-%m-%dT%H:%M")

    duration_min = FlightService.get_route_duration_minutes(origin, destination)
    if duration_min is None:
        return render_template("add_flight.html",flight_num=flight_num, error="No known route between these airports.")

    arr_dt = dep_dt + timedelta(minutes=duration_min)

    free_airplanes = FlightService.get_free_airplanes(dep_dt, arr_dt)
    if not free_airplanes:
        return render_template("add_flight.html",flight_num=flight_num, error="No available airplane for this time window.")

    return render_template(
        "manager_choose_airplane.html",
        flight_num=flight_num,
        origin=origin,
        destination=destination,
        status=status,
        departure_datetime=dep_dt.strftime("%Y-%m-%d %H:%M:%S"),
        arrival_datetime=arr_dt.strftime("%Y-%m-%d %H:%M:%S"),
        duration_min=duration_min,
        airplanes=free_airplanes
    )

@app.route('/manager/add-flight/choose-airplane', methods=['POST'])
@manager_only
def choose_airplane():
    """
    app route for the aircraft selection for a new flight
    - get the chosen aircraft
    - check for available crew (pilots, flight attendants)
    - redirects to the crew selection page
    """
    flight_num = request.form["flight_num"].strip()
    origin = request.form["origin"].strip().upper()
    destination = request.form["destination"].strip().upper()
    status = request.form["status"].strip().lower()
    airplane_id = int(request.form["airplane_id"])

    dep_dt = datetime.strptime(request.form["departure_datetime"], "%Y-%m-%d %H:%M:%S")
    arr_dt = datetime.strptime(request.form["arrival_datetime"], "%Y-%m-%d %H:%M:%S")

    duration_hours = (arr_dt - dep_dt).total_seconds() / 3600.0
    long_flag = 1 if duration_hours > 6 else 0

    plane_size = FlightService.get_plane_size(airplane_id)
    if not plane_size:
        return render_template("manager_choose_airplane.html", error="Invalid airplane id.")

    need_pilots, need_att = FlightService.crew_needs_for_plane(plane_size)

    pilots = FlightService.get_available_pilots(dep_dt, arr_dt, long_flag, origin)
    attendants = FlightService.get_available_attendants(dep_dt, arr_dt, long_flag, origin)

    if len(pilots) < need_pilots or len(attendants) < need_att:
        free_airplanes = FlightService.get_free_airplanes(dep_dt, arr_dt)
        return render_template(
            "manager_choose_airplane.html",
            error="Not enough available crew for this airplane/time (consider different airplane or time).",
            flight_num=flight_num, origin=origin, destination=destination, status=status,
            departure_datetime=dep_dt.strftime("%Y-%m-%d %H:%M:%S"),
            arrival_datetime=arr_dt.strftime("%Y-%m-%d %H:%M:%S"),
            duration_min=int((arr_dt-dep_dt).total_seconds()/60),
            airplanes=free_airplanes
        )

    return render_template(
        "manager_build_crew.html",
        flight_num=flight_num, origin=origin, destination=destination, status=status,
        departure_datetime=dep_dt.strftime("%Y-%m-%d %H:%M:%S"),
        arrival_datetime=arr_dt.strftime("%Y-%m-%d %H:%M:%S"),
        airplane_id=airplane_id,
        plane_size=plane_size,
        long_flag=long_flag,
        need_pilots=need_pilots,
        need_attendants=need_att,
        pilots=pilots,
        attendants=attendants
    )

@app.route('/manager/add-flight/final', methods=['POST'])
@manager_only
def create_flight_final():
    """
    app route for the pricing page of flight classes
    - check again if all data is correct
    - if there are missing workers go back to choose more
    - redirect to set prices
    """
    flight_num = (request.form.get("flight_num") or "").strip()
    origin = (request.form.get("origin") or "").strip().upper()
    destination = (request.form.get("destination") or "").strip().upper()
    status = (request.form.get("status") or "active").strip().lower()
    airplane_id = int(request.form["airplane_id"])

    dep_dt = datetime.strptime(request.form["departure_datetime"], "%Y-%m-%d %H:%M:%S")
    arr_dt = datetime.strptime(request.form["arrival_datetime"], "%Y-%m-%d %H:%M:%S")

    need_pilots = int(request.form["need_pilots"])
    need_att = int(request.form["need_attendants"])

    pilot_ids = request.form.getlist("pilot_ids")
    attendant_ids = request.form.getlist("attendant_ids")


    if len(pilot_ids) != need_pilots or len(attendant_ids) != need_att:
        duration_hours = (arr_dt - dep_dt).total_seconds() / 3600.0
        long_flag = 1 if duration_hours > 6 else 0

        plane_size = FlightService.get_plane_size(airplane_id) or "Small"
        pilots = FlightService.get_available_pilots(dep_dt, arr_dt, long_flag, origin)
        attendants = FlightService.get_available_attendants(dep_dt, arr_dt, long_flag, origin)

        return render_template(
            "manager_build_crew.html",
            error=f"You must select exactly {need_pilots} pilots and {need_att} attendants.",
            flight_num=flight_num,
            origin=origin,
            destination=destination,
            status=status,
            departure_datetime=dep_dt.strftime("%Y-%m-%d %H:%M:%S"),
            arrival_datetime=arr_dt.strftime("%Y-%m-%d %H:%M:%S"),
            airplane_id=airplane_id,
            plane_size=plane_size,
            long_flag=long_flag,
            need_pilots=need_pilots,
            need_attendants=need_att,
            pilots=pilots,
            attendants=attendants
        )

    classes = FlightService.get_classes_for_airplane(airplane_id)

    return render_template(
        "manager_set_prices.html",
        flight_num=flight_num,
        origin=origin,
        destination=destination,
        status=status,
        departure_datetime=dep_dt.strftime("%Y-%m-%d %H:%M:%S"),
        arrival_datetime=arr_dt.strftime("%Y-%m-%d %H:%M:%S"),
        airplane_id=airplane_id,
        pilot_ids=pilot_ids,
        attendant_ids=attendant_ids,
        classes=classes
    )

@app.route('/manager/add-flight/create', methods=['POST'])
@manager_only
def create_flight_after_pricing():
    """
    - creates a new flight with all the given data
    - check if price is valid
    - check if flight is not taken
    redirect to manager home page
    """
    flight_num = (request.form.get("flight_num") or "").strip()
    origin = (request.form.get("origin") or "").strip().upper()
    destination = (request.form.get("destination") or "").strip().upper()
    status = (request.form.get("status") or "active").strip().lower()
    airplane_id = int(request.form["airplane_id"])

    dep_dt = datetime.strptime(request.form["departure_datetime"], "%Y-%m-%d %H:%M:%S")
    arr_dt = datetime.strptime(request.form["arrival_datetime"], "%Y-%m-%d %H:%M:%S")

    pilot_ids = request.form.getlist("pilot_ids")
    attendant_ids = request.form.getlist("attendant_ids")
    crew_ids = [int(x) for x in pilot_ids] + [int(x) for x in attendant_ids]

    classes = FlightService.get_classes_for_airplane(airplane_id)

    prices = []
    for ct in classes:
        raw = (request.form.get(f"price_{ct}") or "").strip()
        try:
            p = float(raw)
            if p < 0:
                raise ValueError
        except ValueError:
            return render_template(
                "manager_set_prices.html",
                error=f"Invalid price for {ct}.",
                flight_num=flight_num, origin=origin, destination=destination, status=status,
                departure_datetime=dep_dt.strftime("%Y-%m-%d %H:%M:%S"),
                arrival_datetime=arr_dt.strftime("%Y-%m-%d %H:%M:%S"),
                airplane_id=airplane_id,
                pilot_ids=pilot_ids, attendant_ids=attendant_ids,
                classes=classes
            )
        prices.append((ct, p))

    ok, err = FlightService.create_flight_with_crew_seats_prices(
        flight_num=flight_num,
        origin=origin,
        destination=destination,
        status=status,
        airplane_id=airplane_id,
        dep_dt=dep_dt,
        arr_dt=arr_dt,
        crew_ids=crew_ids,
        prices=prices
    )
    if not ok:
        return render_template("add_flight.html", error=err or "Failed creating flight.")

    return redirect(url_for("manager_home"))

@app.route("/manager/add_worker", methods=["GET", "POST"])
@manager_only
def add_worker():
    """
    app route for the add worker page
    - get all the values the manager inserted
    - create worker into db
    - if values are not valid, raise error
    redirect to manager home
    """
    if request.method == "GET":
        return render_template("add_worker.html")

    try:
        worker_id = int(request.form.get("worker_id"))
        phone_number = request.form.get("phone_number")
        house_num = int(request.form.get("house_num"))
        street = request.form.get("street")
        city = request.form.get("city")
        f_name_he = request.form.get("f_name_he")
        l_name_he = request.form.get("l_name_he")
        work_start_date = request.form.get("work_start_date")

        role = request.form.get("role")
        lng_flight_approved = 1 if request.form.get("lng_flight_approved") == "1" else 0

        FlightService.create_worker(
            worker_id=worker_id,
            phone_number=phone_number,
            house_num=house_num,
            street=street,
            city=city,
            f_name_he=f_name_he,
            l_name_he=l_name_he,
            work_start_date=work_start_date,
            role=role,
            lng_flight_approved=lng_flight_approved
        )

        return redirect(url_for("manager_home"))

    except ValueError as e:
        if str(e) == "WORKER_ID_TAKEN":
            error = "Worker ID is already taken. Please choose a different ID."
        else:
            error = "Invalid input. Please check the fields."

        return render_template("add_worker.html", error=error)

    except Exception:
        return render_template("add_worker.html", error="Something went wrong. Please try again.")


@app.route("/manager/add_airplane", methods=["GET", "POST"])
@manager_only
def add_airplane():
    """
    app route for the add airplane page
    - get all the values the manager inserted
    redirect to choose classes page
    """
    if request.method == "GET":
        return render_template("add_airplane.html", manufacturer=None,
                           date_of_purchase=None, plane_size=None)

    manufacturer = request.form.get("manufacturer")
    date_of_purchase = request.form.get("date")
    plane_size = request.form.get("plane_size")
    return render_template("choose_classes.html", manufacturer=manufacturer,
                           date_of_purchase=date_of_purchase, plane_size=plane_size)

@app.route("/manager/save_airplane", methods=["POST"])
@manager_only
def save_airplane():
    """
    creates the new airplane with all the values
    redirect to manager home
    """
    manufacturer = request.form.get("manufacturer")
    date_of_purchase = request.form.get("date")
    plane_size = request.form.get("plane_size")

    eco_rows = int(request.form.get("eco_rows"))
    eco_cols = int(request.form.get("eco_cols"))

    bus_rows = bus_cols = None
    if (plane_size or "").lower() != "small":
        bus_rows = int(request.form.get("bus_rows"))
        bus_cols = int(request.form.get("bus_cols"))

    FlightService.create_airplane_with_layout(
        manufacturer=manufacturer,
        date_of_purchase=date_of_purchase,
        plane_size=plane_size,
        eco_rows=eco_rows,
        eco_cols=eco_cols,
        bus_rows=bus_rows,
        bus_cols=bus_cols
    )
    return redirect(url_for("manager_home"))

if __name__ == '__main__':
    app.run(debug=True)