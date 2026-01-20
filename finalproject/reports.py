import queries
from utils import db_cur

def report_cancellation():
    """
    Monthly Cancellation Rate Report - Track cancellation trends
    :return: tuple of arguments
    """
    with db_cur() as cursor:
        cursor.execute(queries.CANCELLATION_RATE_BY_MONTH)
        results = cursor.fetchall()

    months = []
    rates = []
    
    for row in results:
        month, rate = row
        months.append(month)
        rates.append(float(rate) if rate else 0)

    avg_rate = round(sum(rates) / len(rates), 2) if rates else 0
    max_rate = max(rates) if rates else 0
    min_rate = min(rates) if rates else 0

    months_json = str(months).replace("'", '"')
    rates_json = str(rates)

    return avg_rate,max_rate,min_rate,months_json,rates_json,results


def report_operational():
    """
    Operational Summary Report - Shows monthly operations per aircraft
    :return: tuple of arguments
    """
    with db_cur() as cursor:
        cursor.execute(queries.MONTHLY_ACTIVITY_SUMMARY_PER_AIRCRAFT)
        rows = cursor.fetchall()

    aircraft_data = []
    total_utilization = 0
    aircraft_ids = set()

    for row in rows:
        airplane_id, month, flights_done, flights_cancelled, utilization, route = row
        aircraft_data.append({
            'airplane_id': airplane_id,
            'month': month,
            'flights_done': int(flights_done or 0),
            'flights_cancelled': int(flights_cancelled or 0),
            'utilization': float(utilization) if utilization else 0,
            'dominant_route': route or 'N/A'
        })
        total_utilization += (float(utilization) if utilization else 0)
        aircraft_ids.add(airplane_id)

    avg_utilization = round(total_utilization / len(aircraft_data), 2) if aircraft_data else 0
    all_months = sorted(list(set(d['month'] for d in aircraft_data)))

    chart_datasets = []
    colors = ['#0052CC', '#FFB800', '#10B981', '#EF4444', '#8B5CF6']

    for i, aircraft_id in enumerate(sorted(aircraft_ids)):
        plane_data = [d for d in aircraft_data if d['airplane_id'] == aircraft_id]
        by_month = {d['month']:d for d in plane_data}
        util_values = [by_month.get(m, {}).get("utilization", 0) for m in all_months]
        chart_datasets.append({
            'label': f'Aircraft {aircraft_id}',
            'data': util_values,
            'borderColor': colors[i % len(colors)],
            'backgroundColor': colors[i % len(colors)] + '33',
            'tension': 0.4,
            'borderWidth': 2
        })

    return aircraft_data, avg_utilization, len(aircraft_ids), all_months, chart_datasets

def report_revenue():
    """
    Revenue Report - Shows income breakdown by aircraft manufacturer, size, and class
    :return: tuple of arguments
    """
    with db_cur() as cursor:
        cursor.execute(queries.REVENUE_BY_PLANE_INFO)
        rows = cursor.fetchall()

    data = []
    total_revenue = 0

    for row in rows:
        manufacturer, plane_size, class_type, income = row
        data.append({
            'manufacturer': manufacturer,
            'plane_size': plane_size,
            'class_type': class_type,
            'income': float(income)
        })
        total_revenue += float(income)

    labels = [f"{d['manufacturer']} {d['plane_size']}" for d in data]
    economy_data = [d['income'] for d in data if d['class_type'] == 'Economy']
    business_data = [d['income'] for d in data if d['class_type'] == 'Business']

    return data, total_revenue, labels, economy_data, business_data
