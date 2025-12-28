from operator import truediv

from flask import Flask, request, redirect, render_template
import mysql.connector
from contextlib import contextmanager

app = Flask(__name__)

@app.route('/', methods=['POST','GET'])
def home():
    if request.method == 'POST':
        date = request.form.get("date")
        origin_airport = request.form.get("origin")
        destination_airport = request.form.get("destination")
        data = flight_exists(date, origin_airport, destination_airport)
        if data:
           return render_template("order.html",options=data,date=date,origin=origin_airport,destination=destination_airport)
        else:
            return render_template("search_flights.html", error='there are no available flights')
    return render_template("search_flights.html")

@app.route('/login', methods=['POST','GET']) #דף התחברות למערכת כולל לוגו
def login():
    if request.method == 'POST':
        email = request.form.get("email")
        password = request.form.get("password")
        if check_credentials(email, password):
            return render_template('search_flights.html')
        else:
            return render_template('login.html', error = "Wrong username or password, Please try again!")
    else:
        return render_template('login.html')

@app.route('/signup', methods=['POST', 'GET'])
def signup():
    return render_template('signup.html')
@app.route('/order', methods=['POST','GET'])
def order_page():
    if request.method == 'POST':
        selected_flight_num = request.form.get("flight_num")
        return f"Selected flight: {selected_flight_num}"
    return render_template('order.html')



def check_credentials(email, password):
    query = "SELECT password FROM customers WHERE email = %s"
    with db_cur() as cursor:
        cursor.execute(query, (email,))
        row = cursor.fetchone()
        if not row:
            return False
        return row[0] == password

def flight_exists(date, origin_airport, destination_airport):
    query = """
        SELECT
          flight_num,
          DATE_FORMAT(departure_datetime, '%H:%i') AS dep_time,
          DATE_FORMAT(arrival_datetime,   '%H:%i') AS arr_time
        FROM flight
        WHERE origin_airport = %s
          AND destination_airport = %s
          AND DATE(departure_datetime) = %s
          AND status = 'active'
        ORDER BY departure_datetime;
    """
    with db_cur() as cursor:
        cursor.execute(query, (origin_airport, destination_airport, date))
        return cursor.fetchall() or None








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










if __name__ == '__main__':
    app.run(debug=True)