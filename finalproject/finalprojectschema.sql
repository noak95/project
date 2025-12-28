
DROP SCHEMA IF EXISTS FLYTAU;
CREATE SCHEMA FLYTAU;
USE FLYTAU;


CREATE TABLE users (
  email   VARCHAR(255) PRIMARY KEY,
  f_name  VARCHAR(60),
  l_name  VARCHAR(60)
);


CREATE TABLE user_phones (
  email      VARCHAR(255) NOT NULL,
  phone_num  VARCHAR(20)  NOT NULL,
  PRIMARY KEY (email, phone_num),
  FOREIGN KEY (email) REFERENCES users(email)
);


CREATE TABLE customers (
  email         VARCHAR(255) PRIMARY KEY,
  birth_date    DATE,
  sign_up_date  DATE,
  passport_num  VARCHAR(40) NOT NULL UNIQUE,
  password      VARCHAR(255),
  FOREIGN KEY (email) REFERENCES users(email)
);


CREATE TABLE routes (
  origin_airport       VARCHAR(10) NOT NULL,
  destination_airport  VARCHAR(10) NOT NULL,
  duration             INT,
  PRIMARY KEY (origin_airport, destination_airport)
);


CREATE TABLE airplanes (
  airplane_id      INT PRIMARY KEY,
  manufacturer     VARCHAR(80),
  date_of_purchase DATE,
  plane_size       VARCHAR(40)
);

CREATE TABLE class (
  airplane_id  INT NOT NULL,
  class_type   VARCHAR(30) NOT NULL,
  num_rows     INT NOT NULL,
  num_columns  INT NOT NULL,
  PRIMARY KEY (airplane_id, class_type),
  FOREIGN KEY (airplane_id) REFERENCES airplanes(airplane_id)
);

CREATE TABLE seat_position (
  airplane_id    INT NOT NULL,
  class_type     VARCHAR(30) NOT NULL,
  row_num        INT NOT NULL,
  column_letter  CHAR(1) NOT NULL,
  PRIMARY KEY (airplane_id, class_type, row_num, column_letter),
  FOREIGN KEY (airplane_id, class_type) REFERENCES class(airplane_id, class_type)
);


CREATE TABLE flight (
  flight_num          VARCHAR(20) PRIMARY KEY,
  departure_datetime  DATETIME NOT NULL,
  arrival_datetime    DATETIME NOT NULL,
  status              VARCHAR(30),

  origin_airport       VARCHAR(10) NOT NULL,
  destination_airport  VARCHAR(10) NOT NULL,

  airplane_id         INT NOT NULL,

  FOREIGN KEY (origin_airport, destination_airport)
    REFERENCES routes(origin_airport, destination_airport),

  FOREIGN KEY (airplane_id) REFERENCES airplanes(airplane_id),

  
  UNIQUE (flight_num, airplane_id)
);

CREATE TABLE flight_seat (
  flight_num      VARCHAR(20) NOT NULL,
  airplane_id     INT NOT NULL,
  class_type      VARCHAR(30) NOT NULL,
  row_num         INT NOT NULL,
  column_letter   CHAR(1) NOT NULL,
  seat_status     VARCHAR(30),

  PRIMARY KEY (flight_num, airplane_id, class_type, row_num, column_letter),

  FOREIGN KEY (flight_num) REFERENCES flight(flight_num),

  FOREIGN KEY (airplane_id, class_type, row_num, column_letter)
    REFERENCES seat_position(airplane_id, class_type, row_num, column_letter)
);


CREATE TABLE flight_class_price (
  flight_num   VARCHAR(20) NOT NULL,
  airplane_id  INT NOT NULL,
  class_type   VARCHAR(30) NOT NULL,
  price        DECIMAL(10,2) NOT NULL,

  PRIMARY KEY (flight_num, airplane_id, class_type),

  FOREIGN KEY (flight_num, airplane_id)
    REFERENCES flight(flight_num, airplane_id),

  FOREIGN KEY (airplane_id, class_type)
    REFERENCES class(airplane_id, class_type)
);


CREATE TABLE orders (
  order_id        INT PRIMARY KEY,
  email           VARCHAR(255) NOT NULL,
  flight_num      VARCHAR(20) NOT NULL,
  order_date      DATETIME,
  status          VARCHAR(30),
  total_paid      DECIMAL(10,2),
  refund_amount   DECIMAL(10,2),

  FOREIGN KEY (email) REFERENCES users(email),
  FOREIGN KEY (flight_num) REFERENCES flight(flight_num)
);

CREATE TABLE order_seat (
  order_id          INT NOT NULL,
  flight_num        VARCHAR(20) NOT NULL,
  airplane_id       INT NOT NULL,
  class_type        VARCHAR(30) NOT NULL,
  row_num           INT NOT NULL,
  column_letter     CHAR(1) NOT NULL,

  price_at_purchase DECIMAL(10,2) NOT NULL,

  PRIMARY KEY (order_id, flight_num, airplane_id, class_type, row_num, column_letter),

  FOREIGN KEY (order_id) REFERENCES orders(order_id),

  FOREIGN KEY (flight_num, airplane_id, class_type, row_num, column_letter)
    REFERENCES flight_seat(flight_num, airplane_id, class_type, row_num, column_letter),

  
  UNIQUE (flight_num, airplane_id, class_type, row_num, column_letter)
);


CREATE TABLE workers (
  worker_id        INT PRIMARY KEY,
  phone_number     VARCHAR(20),

  house_num        VARCHAR(20),
  street           VARCHAR(80),
  city             VARCHAR(80),

  f_name_he        VARCHAR(60),
  l_name_he        VARCHAR(60),

  work_start_date  DATE
);

CREATE TABLE managers (
  worker_id   INT PRIMARY KEY,
  password    VARCHAR(255) NOT NULL,
  FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
);

CREATE TABLE pilots (
  worker_id            INT PRIMARY KEY,
  lng_flight_approved  BOOLEAN,
  FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
);

CREATE TABLE flight_attendants (
  worker_id            INT PRIMARY KEY,
  lng_flight_approved  BOOLEAN,
  FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
);

CREATE TABLE flight_worker (
  flight_num  VARCHAR(20) NOT NULL,
  worker_id   INT NOT NULL,
  PRIMARY KEY (flight_num, worker_id),
  FOREIGN KEY (flight_num) REFERENCES flight(flight_num),
  FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
);

USE FLYTAU;


INSERT INTO users (email, f_name, l_name) VALUES
('noa.reg1@flytau.com', 'Noa', 'Registered1'),
('noa.reg2@flytau.com', 'Noa', 'Registered2'),
('guest1@flytau.com', 'Guest', 'One'),
('guest2@flytau.com', 'Guest', 'Two');


INSERT INTO user_phones (email, phone_num) VALUES
('noa.reg1@flytau.com', '050-1111111'),
('noa.reg1@flytau.com', '052-1111111'),
('noa.reg2@flytau.com', '050-2222222'),
('guest1@flytau.com', '054-3333333'),
('guest2@flytau.com', '054-4444444'),
('guest2@flytau.com', '058-4444444');


INSERT INTO customers (email, birth_date, sign_up_date, passport_num, password) VALUES
('noa.reg1@flytau.com', '2003-05-10', '2025-12-01', 'P000000001', 'pass_reg1'),
('noa.reg2@flytau.com', '2002-11-20', '2025-12-02', 'P000000002', 'pass_reg2');


INSERT INTO airplanes (airplane_id, manufacturer, date_of_purchase, plane_size) VALUES
(1, 'Airbus',  '2020-01-10', 'Small'),
(2, 'Boeing',  '2021-03-15', 'Small'),
(3, 'Embraer', '2019-06-20', 'Small'),
(4, 'Airbus',  '2022-09-01', 'Small'),
(5, 'Boeing',  '2018-12-30', 'Small'),
(6, 'Airbus',  '2023-04-05', 'Small');


INSERT INTO class (airplane_id, class_type, num_rows, num_columns) VALUES
(1, 'Economy', 2, 3), (1, 'Business', 1, 2),
(2, 'Economy', 2, 3), (2, 'Business', 1, 2),
(3, 'Economy', 2, 3), (3, 'Business', 1, 2),
(4, 'Economy', 2, 3), (4, 'Business', 1, 2),
(5, 'Economy', 2, 3), (5, 'Business', 1, 2),
(6, 'Economy', 2, 3), (6, 'Business', 1, 2);


INSERT INTO seat_position (airplane_id, class_type, row_num, column_letter) VALUES
-- airplane 1
(1,'Economy',1,'A'),(1,'Economy',1,'B'),(1,'Economy',1,'C'),
(1,'Economy',2,'A'),(1,'Economy',2,'B'),(1,'Economy',2,'C'),
(1,'Business',1,'A'),(1,'Business',1,'B'),
-- airplane 2
(2,'Economy',1,'A'),(2,'Economy',1,'B'),(2,'Economy',1,'C'),
(2,'Economy',2,'A'),(2,'Economy',2,'B'),(2,'Economy',2,'C'),
(2,'Business',1,'A'),(2,'Business',1,'B'),
-- airplane 3
(3,'Economy',1,'A'),(3,'Economy',1,'B'),(3,'Economy',1,'C'),
(3,'Economy',2,'A'),(3,'Economy',2,'B'),(3,'Economy',2,'C'),
(3,'Business',1,'A'),(3,'Business',1,'B'),
-- airplane 4
(4,'Economy',1,'A'),(4,'Economy',1,'B'),(4,'Economy',1,'C'),
(4,'Economy',2,'A'),(4,'Economy',2,'B'),(4,'Economy',2,'C'),
(4,'Business',1,'A'),(4,'Business',1,'B'),
-- airplane 5
(5,'Economy',1,'A'),(5,'Economy',1,'B'),(5,'Economy',1,'C'),
(5,'Economy',2,'A'),(5,'Economy',2,'B'),(5,'Economy',2,'C'),
(5,'Business',1,'A'),(5,'Business',1,'B'),
-- airplane 6
(6,'Economy',1,'A'),(6,'Economy',1,'B'),(6,'Economy',1,'C'),
(6,'Economy',2,'A'),(6,'Economy',2,'B'),(6,'Economy',2,'C'),
(6,'Business',1,'A'),(6,'Business',1,'B');


INSERT INTO routes (origin_airport, destination_airport, duration) VALUES
('TLV','ATH', 150),
('TLV','LHR', 300),
('TLV','JFK', 660),
('ATH','LHR', 220);

INSERT INTO flight (
  flight_num, departure_datetime, arrival_datetime, status,
  origin_airport, destination_airport, airplane_id
) VALUES
('F1001', '2026-01-05 08:00:00', '2026-01-05 10:30:00', 'active', 'TLV', 'ATH', 1),
('F1002', '2026-01-06 12:00:00', '2026-01-06 17:00:00', 'active', 'TLV', 'LHR', 2),
('F1003', '2026-01-07 23:00:00', '2026-01-08 10:00:00', 'active', 'TLV', 'JFK', 3),
('F1004', '2026-01-08 09:00:00', '2026-01-08 12:40:00', 'active', 'ATH', 'LHR', 4);


INSERT INTO flight_seat (flight_num, airplane_id, class_type, row_num, column_letter, seat_status) VALUES
('F1001',1,'Economy',1,'A','available'),
('F1001',1,'Economy',1,'B','available'),
('F1002',2,'Economy',1,'A','available'),
('F1002',2,'Business',1,'A','available'),
('F1003',3,'Economy',1,'A','available'),
('F1003',3,'Business',1,'A','available'),
('F1004',4,'Economy',1,'A','available'),
('F1004',4,'Economy',1,'B','available');
