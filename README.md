# FlyTAU – Flight Management System
## Project overview
- FlyTau is a flight managment and booking system built with Flask and MySQL.
The system supports users and managers, enabling flight search, seat booking, order managment and full managerial control over flights, crew, airplanes and reports viewing.
---
## Roles
### user / customer
- login + signup (customers) using email
- Search flights by route and date  
- Select number of passengers  
- View seat map and book seats  
- View personal order history (customer)
- Cancel orders according to business rules

### Manager
- Secure login using worker ID  
- View all flights (filter by status)  
- Create new flights (route, airplane, crew, pricing for classes)
- Assign crew based on airplane size & flight duration
- Cancel flights (with 72-hour rule)  
- Add new employees (pilots / attendants)  
- Add new airplanes to the flee
- View system-level reports and analytics

---

## Project Structure
  finalproject/
  │
  ├── static/
  │   ├── images/              
  │   └── styles.css          
  │
  ├── templates/
  │   ├── *.html               
  │
  ├── flask_session_data/       
  ├── __pycache__/              
  │
  ├── main.py                   
  ├── utils.py                  
  ├── queries.py                
  ├── reports.py                
  ├── FLYTAU_final.sql          
  │
  └── README.md                 
  
## DATABASE
**MySQL** -
Schema includes: Users, Customers, Managers, Flights, Routes, Airplanes, Seats, Orders, Order Seats, Crew (Pilots, Flight Attendants)

## Technologics Used
- Python 3
- Flask
- MySQL
- HTML + Jinja2
- CSS
- Flask-Session

## Design Highlights
- Routes (main.py)
- Logic queries (queries.py)
- Utilities (utils.py)
- Manager Reports (reports.py)
- Role-based access control via decorators

## Author
### Yuval Amster ###
### Noa Klein ###
### Sagi Avni ###
- Industrial Engineering & Managment
- Final Project - Database and Information Systems






