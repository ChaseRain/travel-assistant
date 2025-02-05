import re
import sqlite3
from datetime import date, datetime
from typing import Optional

import numpy as np
import openai
import pytz
import requests
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from app.core.config import settings

# 常量定义
ERROR_NO_PASSENGER_ID = "No passenger ID configured."
ERROR_DATE_ORDER = "结束日期必须晚于开始日期。"
ERROR_DATE_CONFLICT = "所选日期与其他预订冲突。"
ERROR_24H_LIMIT = "无法取消开始前24小时内的预订。"
ERROR_FLIGHT_3H_LIMIT = "不允许改签至起飞前3小时内的航班。"
ERROR_NOT_FOUND = "未找到指定{type}。"
ERROR_NOT_OWNER = "当前登录的乘客(ID: {id})不是{type} {no} 的所有者"
TIMEZONE = "Etc/GMT-3"

# 时间常量（秒）
HOURS_24 = 24 * 3600
HOURS_3 = 3 * 3600

# 日期格式常量
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DATETIME_FORMAT_WITH_MICROSECONDS = "%Y-%m-%d %H:%M:%S.%f"
DATE_FORMAT = "%Y-%m-%d"

# SQL查询常量
SQL_CHECK_FLIGHT = """
    SELECT flight_id, flight_no, departure_airport, arrival_airport,
           scheduled_departure, scheduled_arrival,
           actual_departure, actual_arrival, status
    FROM flights 
    WHERE flight_id = ?
"""

SQL_CHECK_BOOKING_CONFLICT = """
    SELECT COUNT(*) FROM {table}
    WHERE id != ? 
    AND location = ?
    AND booked = 1
    AND (
        (start_date BETWEEN ? AND ?)
        OR (end_date BETWEEN ? AND ?)
        OR (start_date <= ? AND end_date >= ?)
    )
"""

###################
# 1. 航班相关工具 #
###################

@tool
def check_flight_status(flight_id: int) -> dict:
    """查询航班状态信息。"""
    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    # 获取基本航班信息
    cursor.execute(SQL_CHECK_FLIGHT, (flight_id,))
    flight = cursor.fetchone()
    
    if not flight:
        cursor.close()
        conn.close()
        return {"error": "未找到指定航班。"}

    column_names = [column[0] for column in cursor.description]
    result = dict(zip(column_names, flight))

    # 获取座位分配信息
    cursor.execute(
        """
        SELECT 
            bp.seat_no,
            t.passenger_id,
            tf.fare_conditions
        FROM boarding_passes bp
        JOIN ticket_flights tf ON bp.ticket_no = tf.ticket_no AND bp.flight_id = tf.flight_id
        JOIN tickets t ON t.ticket_no = bp.ticket_no
        WHERE bp.flight_id = ?
        """,
        (flight_id,)
    )
    
    seat_assignments = [
        {
            "seat_no": row[0],
            "passenger_id": row[1],
            "fare_conditions": row[2]
        }
        for row in cursor.fetchall()
    ]
    
    result["seat_assignments"] = seat_assignments

    cursor.close()
    conn.close()

    return result

@tool
def get_available_seats(flight_id: int) -> list[dict]:
    """获取指定航班的可用座位信息。"""
    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    # 获取已分配的座位
    cursor.execute(
        """
        SELECT seat_no
        FROM boarding_passes
        WHERE flight_id = ?
        """,
        (flight_id,)
    )
    occupied_seats = {row[0] for row in cursor.fetchall()}

    # 获取航班的所有可能座位
    cursor.execute(
        """
        SELECT aircraft_code
        FROM flights f
        JOIN aircrafts a ON f.aircraft_code = a.aircraft_code
        WHERE flight_id = ?
        """,
        (flight_id,)
    )
    aircraft = cursor.fetchone()
    
    if not aircraft:
        cursor.close()
        conn.close()
        return []

    cursor.execute(
        """
        SELECT seat_no, fare_conditions
        FROM seats
        WHERE aircraft_code = ?
        """,
        (aircraft[0],)
    )
    all_seats = cursor.fetchall()
    
    available_seats = [
        {"seat_no": seat[0], "fare_conditions": seat[1]}
        for seat in all_seats
        if seat[0] not in occupied_seats
    ]

    cursor.close()
    conn.close()

    return available_seats

@tool
def update_ticket_to_new_flight(
    ticket_no: str, 
    new_flight_id: int, 
    *, 
    config: RunnableConfig
) -> str:
    """更新用户的机票到新航班。"""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError(ERROR_NO_PASSENGER_ID)

    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT departure_airport, arrival_airport, scheduled_departure FROM flights WHERE flight_id = ?",
        (new_flight_id,),
    )
    new_flight = cursor.fetchone()
    if not new_flight:
        cursor.close()
        conn.close()
        return "无效的新航班ID。"
    
    column_names = [column[0] for column in cursor.description]
    new_flight_dict = dict(zip(column_names, new_flight))
    timezone = pytz.timezone(TIMEZONE)
    current_time = datetime.now(tz=timezone)
    departure_time = parse_datetime(new_flight_dict["scheduled_departure"])
    time_until = (departure_time - current_time).total_seconds()
    if time_until < HOURS_3:
        return f"{ERROR_FLIGHT_3H_LIMIT}选择的航班起飞时间为 {departure_time}。"

    cursor.execute(
        "SELECT flight_id FROM ticket_flights WHERE ticket_no = ?", 
        (ticket_no,)
    )
    current_flight = cursor.fetchone()
    if not current_flight:
        cursor.close()
        conn.close()
        return "未找到指定票号的机票。"

    # 检查登录用户是否拥有此机票
    cursor.execute(
        "SELECT * FROM tickets WHERE ticket_no = ? AND passenger_id = ?",
        (ticket_no, passenger_id),
    )
    current_ticket = cursor.fetchone()
    if not current_ticket:
        cursor.close()
        conn.close()
        return f"{ERROR_NOT_OWNER.format(type='机票', id=passenger_id, no=ticket_no)}"

    # 更新机票航班信息
    cursor.execute(
        "UPDATE ticket_flights SET flight_id = ? WHERE ticket_no = ?",
        (new_flight_id, ticket_no),
    )
    conn.commit()

    cursor.close()
    conn.close()
    return "机票更改成功。"

@tool
def cancel_ticket(
    ticket_no: str,
    *,
    config: RunnableConfig
) -> str:
    """取消用户的机票。"""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError(ERROR_NO_PASSENGER_ID)

    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    # 检查机票是否存在且属于当前用户
    cursor.execute(
        """
        SELECT t.*, f.scheduled_departure 
        FROM tickets t
        JOIN ticket_flights tf ON t.ticket_no = tf.ticket_no
        JOIN flights f ON tf.flight_id = f.flight_id
        WHERE t.ticket_no = ? AND t.passenger_id = ?
        """,
        (ticket_no, passenger_id),
    )
    ticket = cursor.fetchone()
    
    if not ticket:
        cursor.close()
        conn.close()
        return f"{ERROR_NOT_FOUND.format(type='机票', no=ticket_no)}"

    # 检查航班起飞时间
    timezone = pytz.timezone(TIMEZONE)
    current_time = datetime.now(tz=timezone)
    departure_time = parse_datetime(ticket[-1])
    time_until = (departure_time - current_time).total_seconds()
    
    if time_until < HOURS_24:  # 24小时
        return f"{ERROR_24H_LIMIT}入住时间为 {departure_time}。"

    # 删除相关记录
    cursor.execute("DELETE FROM boarding_passes WHERE ticket_no = ?", (ticket_no,))
    cursor.execute("DELETE FROM ticket_flights WHERE ticket_no = ?", (ticket_no,))
    cursor.execute("DELETE FROM tickets WHERE ticket_no = ?", (ticket_no,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return "机票取消成功。"

###################
# 2. 酒店相关工具 #
###################

@tool
def search_hotels(
    location: str,
    checkin_date: date | datetime,
    checkout_date: date | datetime,
    price_tier: Optional[str] = None,
) -> list[dict]:
    """搜索指定地点和日期的酒店。"""
    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    query = "SELECT * FROM hotels WHERE location = ?"
    params = [location]

    if price_tier:
        query += " AND price_tier = ?"
        params.append(price_tier)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    column_names = [column[0] for column in cursor.description]
    results = [dict(zip(column_names, row)) for row in rows]

    cursor.close()
    conn.close()

    return results

@tool
def book_hotel(hotel_id: int) -> str:
    """预订指定ID的酒店。"""
    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM hotels WHERE id = ?", (hotel_id,))
    hotel = cursor.fetchone()
    if not hotel:
        cursor.close()
        conn.close()
        return "找不到指定ID的酒店。"

    cursor.execute(
        "UPDATE hotels SET booked = 1 WHERE id = ?",
        (hotel_id,)
    )
    conn.commit()

    cursor.close() 
    conn.close()
    return "酒店预订成功。"

@tool
def update_hotel(
    hotel_id: int,
    new_checkin_date: date | datetime,
    new_checkout_date: date | datetime,
    *,
    config: RunnableConfig
) -> str:
    """更新酒店预订的日期。"""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError(ERROR_NO_PASSENGER_ID)

    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    # 检查酒店预订是否存在且属于当前用户
    cursor.execute(
        """
        SELECT * FROM hotels 
        WHERE id = ? AND passenger_id = ?
        """,
        (hotel_id, passenger_id),
    )
    hotel = cursor.fetchone()
    
    if not hotel:
        cursor.close()
        conn.close()
        return f"{ERROR_NOT_FOUND.format(type='酒店预订', no=hotel_id)}"

    # 检查新的预订日期是否有效
    if new_checkout_date <= new_checkin_date:
        cursor.close()
        conn.close()
        return "退房日期必须晚于入住日期。"

    # 检查新日期是否与其他预订冲突
    cursor.execute(
        SQL_CHECK_BOOKING_CONFLICT.format(table='hotels'),
        (
            hotel_id,
            hotel["location"],
            new_checkin_date,
            new_checkout_date,
            new_checkin_date,
            new_checkout_date,
            new_checkin_date,
            new_checkout_date,
        ),
    )
    conflicts = cursor.fetchone()[0]
    if conflicts > 0:
        cursor.close()
        conn.close()
        return ERROR_DATE_CONFLICT

    # 检查变更时间限制
    timezone = pytz.timezone(TIMEZONE)
    current_time = datetime.now(tz=timezone)
    
    # 处理日期或datetime输入
    if isinstance(new_checkin_date, str):
        checkin_time = parse_datetime(new_checkin_date)
    else:
        checkin_time = new_checkin_date
        if checkin_time.tzinfo is None:
            checkin_time = timezone.localize(checkin_time)
            
    time_until = (checkin_time - current_time).total_seconds()
    
    if time_until < HOURS_24:  # 24小时
        return f"{ERROR_24H_LIMIT}入住时间为 {checkin_time}。"

    # 更新酒店预订日期
    cursor.execute(
        """
        UPDATE hotels 
        SET checkin_date = ?, checkout_date = ?
        WHERE id = ?
        """,
        (new_checkin_date, new_checkout_date, hotel_id),
    )
    conn.commit()

    cursor.close()
    conn.close()
    return "酒店预订日期更新成功。"

@tool
def cancel_hotel(
    hotel_id: int,
    *,
    config: RunnableConfig
) -> str:
    """取消酒店预订。"""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError(ERROR_NO_PASSENGER_ID)

    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    # 检查酒店预订是否存在且属于当前用户
    cursor.execute(
        """
        SELECT *, checkin_date 
        FROM hotels 
        WHERE id = ? AND passenger_id = ?
        """,
        (hotel_id, passenger_id),
    )
    hotel = cursor.fetchone()
    
    if not hotel:
        cursor.close()
        conn.close()
        return f"{ERROR_NOT_FOUND.format(type='酒店预订', no=hotel_id)}"

    # 检查入住时间
    timezone = pytz.timezone(TIMEZONE)
    current_time = datetime.now(tz=timezone)
    checkin_time = parse_datetime(hotel["checkin_date"])
    time_until = (checkin_time - current_time).total_seconds()
    
    if time_until < HOURS_24:  # 24小时
        return f"{ERROR_24H_LIMIT}入住时间为 {checkin_time}。"

    # 删除酒店预订记录
    cursor.execute(
        """
        DELETE FROM hotels 
        WHERE id = ? AND passenger_id = ?
        """,
        (hotel_id, passenger_id),
    )
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return "酒店预订取消成功。"

###################
# 3. 租车相关工具 #
###################

@tool
def search_car_rentals(
    location: str,
    start_date: date | datetime,
    end_date: date | datetime,
    price_tier: Optional[str] = None,
) -> list[dict]:
    """搜索指定地点和日期的租车选项。"""
    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    query = "SELECT * FROM car_rentals WHERE location = ?"
    params = [location]

    if price_tier:
        query += " AND price_tier = ?"
        params.append(price_tier)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    column_names = [column[0] for column in cursor.description]
    results = [dict(zip(column_names, row)) for row in rows]

    cursor.close()
    conn.close()

    return results

@tool
def book_car_rental(rental_id: int) -> str:
    """预订指定ID的租车。"""
    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM car_rentals WHERE id = ?", (rental_id,))
    rental = cursor.fetchone()
    if not rental:
        cursor.close()
        conn.close()
        return "找不到指定ID的租车。"

    cursor.execute(
        "UPDATE car_rentals SET booked = 1 WHERE id = ?",
        (rental_id,)
    )
    conn.commit()

    cursor.close()
    conn.close()
    return "租车预订成功。"

@tool
def update_car_rental(
    rental_id: int,
    new_start_date: date | datetime,
    new_end_date: date | datetime,
    *,
    config: RunnableConfig
) -> str:
    """更新租车预订的日期。"""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError(ERROR_NO_PASSENGER_ID)

    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    # 检查租车记录是否存在且属于当前用户
    cursor.execute(
        """
        SELECT * FROM car_rentals 
        WHERE id = ? AND passenger_id = ?
        """,
        (rental_id, passenger_id),
    )
    rental = cursor.fetchone()
    
    if not rental:
        cursor.close()
        conn.close()
        return f"{ERROR_NOT_FOUND.format(type='租车记录', no=rental_id)}"

    # 检查新的租车日期是否有效
    if new_end_date <= new_start_date:
        cursor.close()
        conn.close()
        return ERROR_DATE_ORDER

    # 检查新日期是否与其他预订冲突
    cursor.execute(
        SQL_CHECK_BOOKING_CONFLICT.format(table='car_rentals'),
        (
            rental_id,
            rental["location"],
            new_start_date,
            new_end_date,
            new_start_date,
            new_end_date,
            new_start_date,
            new_end_date,
        ),
    )
    conflicts = cursor.fetchone()[0]
    if conflicts > 0:
        cursor.close()
        conn.close()
        return ERROR_DATE_CONFLICT

    # 更新租车日期
    cursor.execute(
        """
        UPDATE car_rentals 
        SET start_date = ?, end_date = ?
        WHERE id = ?
        """,
        (new_start_date, new_end_date, rental_id),
    )
    conn.commit()

    cursor.close()
    conn.close()
    return "租车日期更新成功。"

@tool
def cancel_car_rental(
    rental_id: int,
    *,
    config: RunnableConfig
) -> str:
    """取消租车预订。"""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError(ERROR_NO_PASSENGER_ID)

    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    # 检查租车记录是否存在且属于当前用户
    cursor.execute(
        """
        SELECT *, start_date 
        FROM car_rentals 
        WHERE id = ? AND passenger_id = ?
        """,
        (rental_id, passenger_id),
    )
    rental = cursor.fetchone()
    
    if not rental:
        cursor.close()
        conn.close()
        return f"{ERROR_NOT_FOUND.format(type='租车记录', no=rental_id)}"

    # 检查租车开始时间
    timezone = pytz.timezone(TIMEZONE)
    current_time = datetime.now(tz=timezone)
    start_time = parse_datetime(rental["start_date"])
    time_until = (start_time - current_time).total_seconds()
    
    if time_until < HOURS_24:  # 24小时
        return f"{ERROR_24H_LIMIT}租车开始时间为 {start_time}。"

    # 删除租车记录
    cursor.execute(
        """
        DELETE FROM car_rentals 
        WHERE id = ? AND passenger_id = ?
        """,
        (rental_id, passenger_id),
    )
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return "租车预订取消成功。"

#######################
# 4. 旅游活动相关工具 #
#######################

@tool
def search_trip_recommendations(
    location: str,
    start_date: date | datetime,
    end_date: date | datetime,
    keywords: Optional[str] = None,
) -> list[dict]:
    """搜索指定地点和日期的旅游活动推荐。"""
    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    query = "SELECT * FROM trip_recommendations WHERE location = ?"
    params = [location]

    if keywords:
        # 简单的关键词匹配
        query += " AND (description LIKE ? OR name LIKE ?)"
        keyword_pattern = f"%{keywords}%"
        params.extend([keyword_pattern, keyword_pattern])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    column_names = [column[0] for column in cursor.description]
    results = [dict(zip(column_names, row)) for row in rows]

    cursor.close()
    conn.close()

    return results

@tool
def book_excursion(excursion_id: int) -> str:
    """预订指定ID的旅游活动。"""
    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM trip_recommendations WHERE id = ?", (excursion_id,))
    excursion = cursor.fetchone()
    if not excursion:
        cursor.close()
        conn.close()
        return "找不到指定ID的旅游活动。"

    cursor.execute(
        "UPDATE trip_recommendations SET booked = 1 WHERE id = ?",
        (excursion_id,)
    )
    conn.commit()

    cursor.close()
    conn.close()
    return "旅游活动预订成功。"

@tool
def update_excursion(
    excursion_id: int,
    new_start_date: date | datetime,
    new_end_date: date | datetime,
    *,
    config: RunnableConfig
) -> str:
    """更新旅游活动预订的日期。"""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError(ERROR_NO_PASSENGER_ID)

    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    # 检查旅游活动预订是否存在且属于当前用户
    cursor.execute(
        """
        SELECT * FROM trip_recommendations 
        WHERE id = ? AND passenger_id = ?
        """,
        (excursion_id, passenger_id),
    )
    excursion = cursor.fetchone()
    
    if not excursion:
        cursor.close()
        conn.close()
        return f"{ERROR_NOT_FOUND.format(type='旅游活动预订', no=excursion_id)}"

    # 检查新的预订日期是否有效
    if new_end_date <= new_start_date:
        cursor.close()
        conn.close()
        return ERROR_DATE_ORDER

    # 检查新日期是否与其他预订冲突
    cursor.execute(
        SQL_CHECK_BOOKING_CONFLICT.format(table='trip_recommendations'),
        (
            excursion_id,
            excursion["location"],
            new_start_date,
            new_end_date,
            new_start_date,
            new_end_date,
            new_start_date,
            new_end_date,
        ),
    )
    conflicts = cursor.fetchone()[0]
    if conflicts > 0:
        cursor.close()
        conn.close()
        return ERROR_DATE_CONFLICT

    # 检查变更时间限制
    timezone = pytz.timezone(TIMEZONE)
    current_time = datetime.now(tz=timezone)
    start_time = parse_datetime(str(new_start_date))
    time_until = (start_time - current_time).total_seconds()
    
    if time_until < HOURS_24:  # 24小时
        return f"{ERROR_24H_LIMIT}开始时间为 {start_time}。"

    # 更新旅游活动预订日期
    cursor.execute(
        """
        UPDATE trip_recommendations 
        SET start_date = ?, end_date = ?
        WHERE id = ?
        """,
        (new_start_date, new_end_date, excursion_id),
    )
    conn.commit()

    cursor.close()
    conn.close()
    return "旅游活动预订日期更新成功。"

@tool
def cancel_excursion(
    excursion_id: int,
    *,
    config: RunnableConfig
) -> str:
    """取消旅游活动预订。"""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError(ERROR_NO_PASSENGER_ID)

    conn = sqlite3.connect(settings.DATABASE_URL)
    cursor = conn.cursor()

    # 检查旅游活动预订是否存在且属于当前用户
    cursor.execute(
        """
        SELECT *, start_date 
        FROM trip_recommendations 
        WHERE id = ? AND passenger_id = ?
        """,
        (excursion_id, passenger_id),
    )
    excursion = cursor.fetchone()
    
    if not excursion:
        cursor.close()
        conn.close()
        return f"{ERROR_NOT_FOUND.format(type='旅游活动预订', no=excursion_id)}"

    # 检查活动开始时间
    timezone = pytz.timezone(TIMEZONE)
    current_time = datetime.now(tz=timezone)
    start_time = parse_datetime(excursion["start_date"])
    time_until = (start_time - current_time).total_seconds()
    
    if time_until < HOURS_24:  # 24小时
        return f"{ERROR_24H_LIMIT}活动开始时间为 {start_time}。"

    # 删除旅游活动预订记录
    cursor.execute(
        """
        DELETE FROM trip_recommendations 
        WHERE id = ? AND passenger_id = ?
        """,
        (excursion_id, passenger_id),
    )
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return "旅游活动预订取消成功。"

###################
# 5. 政策查询工具 #
###################

@tool
def lookup_policy(query: str) -> str:
    """查询公司政策。"""
    response = requests.get(
        "https://storage.googleapis.com/benchmarks-artifacts/travel-db/swiss_faq.md"
    )
    response.raise_for_status()
    faq_text = response.text

    docs = [{
        "page_content": txt
    } for txt in re.split(r"(?=\n##)", faq_text)]

    # 使用向量检索查找相关政策
    client = openai.Client(api_key=settings.OPENAI_API_KEY)
    retriever = VectorStoreRetriever.from_docs(docs, client)
    results = retriever.query(query)

    if not results:
        return "未找到相关政策。"

    return results[0]["page_content"]

###################
# 6. 错误处理工具 #
###################

@tool
def handle_tool_error(error: str) -> str:
    """处理工具执行过程中的错误。"""
    # 常见错误信息的中文映射
    error_mappings = {
        "No passenger ID configured": "未配置乘客ID",
        "Invalid date format": "日期格式无效",
        "Database connection error": "数据库连接错误",
        "Record not found": "未找到记录",
        "Permission denied": "权限不足",
        "Booking conflict": "预订时间冲突",
        "Invalid input": "输入无效",
        "Operation timeout": "操作超时",
        "Service unavailable": "服务不可用",
    }

    # 尝试匹配具体错误
    for eng_error, cn_error in error_mappings.items():
        if eng_error.lower() in error.lower():
            return f"发生错误: {cn_error}。请检查输入并重试。"

    # 如果是ValueError类型的错误
    if "ValueError" in error:
        return "输入值无效。请检查所有必填字段并确保格式正确。"
    
    # 如果是数据库相关错误
    if any(db_error in error.lower() for db_error in ["sqlite", "database", "sql"]):
        return "数据库操作出错。请稍后重试。"
    
    # 如果是日期相关错误
    if any(date_error in error.lower() for date_error in ["date", "time", "datetime"]):
        return "日期格式错误或日期无效。请使用正确的日期格式。"
    
    # 如果是权限相关错误
    if any(perm_error in error.lower() for perm_error in ["permission", "access", "denied"]):
        return "您没有执行此操作的权限。请确认您的身份验证是否正确。"
    
    # 如果是预订冲突
    if any(booking_error in error.lower() for booking_error in ["conflict", "overlap", "already booked"]):
        return "预订发生冲突。请选择其他时间或检查现有预订。"
    
    # 默认错误信息
    return f"发生未知错误: {error}。请联系客服获取帮助。"

def parse_datetime(date_str: str, timezone_name: str = TIMEZONE) -> datetime:
    """灵活解析日期时间字符串，支持多种格式。
    
    Args:
        date_str: 日期时间字符串
        timezone_name: 时区名称，默认使用系统配置的时区
        
    Returns:
        datetime: 解析后的datetime对象(带时区信息)
    """
    tz = pytz.timezone(timezone_name)
    
    # 尝试不同的日期格式
    formats = [
        DATETIME_FORMAT,
        DATETIME_FORMAT_WITH_MICROSECONDS,
        DATE_FORMAT,
        "%Y-%m-%d %H:%M:%S%z",  # 带时区
        "%Y-%m-%d %H:%M:%S.%f%z",  # 带微秒和时区
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # 如果解析出的datetime没有时区信息，添加时区
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            return dt
        except ValueError:
            continue
            
    raise ValueError(f"无法解析日期时间字符串: {date_str}")