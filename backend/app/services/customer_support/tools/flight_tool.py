import sqlite3
import logging
from datetime import date, datetime
from typing import Optional
import os
from pathlib import Path

import pytz
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from app.core.config import settings

# 使用相对路径
project_root = Path(__file__).parent.parent.parent.parent.parent  # 回到项目根目录
db_path = (project_root / settings.DATABASE_URL.replace('sqlite:///', '')).resolve()
db = settings.DATABASE_URL
ERROR_NO_PASSENGER_ID = "No passenger ID configured."

def get_db_connection():
    """创建数据库连接并返回连接和游标"""
    logger = logging.getLogger(__name__)
    try:
        # 确保数据库目录存在
        db_dir = os.path.dirname(str(db_path))
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"创建数据库目录: {db_dir}")
        
        logger.info(f"尝试连接数据库: {db}")
        logger.info(f"实际数据库路径: {db_path}")
        conn = sqlite3.connect(str(db_path))
        
        # 测试数据库连接并检查表
        cursor = conn.cursor()
        
        # 查询所有表名
        cursor.execute("""
            SELECT name 
            FROM sqlite_master 
            WHERE type='table';
        """)
        tables = cursor.fetchall()
        logger.info("数据库中的所有表：")
        for table in tables:
            logger.info(f"- {table[0]}")
            
            # 可选：查看表结构
            cursor.execute(f"PRAGMA table_info({table[0]})")
            columns = cursor.fetchall()
            logger.info(f"{table[0]} 表的结构:")
            for col in columns:
                logger.info(f"  - {col[1]} ({col[2]})")
        
        return conn
    except sqlite3.Error as e:
        logger.error(f"数据库连接错误: {str(e)}")
        logger.error(f"数据库路径: {db_path}")
        logger.error(f"当前工作目录: {os.getcwd()}")
        raise

@tool
def fetch_user_flight_information(config: RunnableConfig) -> list[dict]:
    """Fetch all tickets for the user along with corresponding flight information and seat assignments.

    Returns:
        A list of dictionaries where each dictionary contains the ticket details,
        associated flight details, and the seat assignments for each ticket belonging to the user.
    """
    logger = logging.getLogger(__name__)
    
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        logger.error("航空：未提供乘客ID")
        raise ValueError(ERROR_NO_PASSENGER_ID)

    logger.info(f"航空：正在查询乘客 {passenger_id} 的航班信息")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 查询所有表名
            cursor.execute("""
                SELECT name 
                FROM sqlite_master 
                WHERE type='table';
            """)
            tables = cursor.fetchall()
            logger.info("数据库中的所有表：")
            for table in tables:
                logger.info(f"- {table[0]}")
            
            # 检查tickets表是否存在
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='tickets';
            """)
            if not cursor.fetchone():
                logger.error("tickets表不存在！")
                return []
            
            # 检查该乘客是否存在
            cursor.execute("SELECT * FROM tickets WHERE passenger_id = ?", (passenger_id,))
            if not cursor.fetchone():
                logger.error(f"未找到乘客ID为 {passenger_id} 的记录")
                return []
                
            # 原有的查询
            query = """
            SELECT 
                t.ticket_no, t.book_ref,
                f.flight_id, f.flight_no, f.departure_airport, f.arrival_airport, 
                f.scheduled_departure, f.scheduled_arrival,
                bp.seat_no, tf.fare_conditions
            FROM 
                tickets t
                JOIN ticket_flights tf ON t.ticket_no = tf.ticket_no
                JOIN flights f ON tf.flight_id = f.flight_id
                LEFT JOIN boarding_passes bp ON bp.ticket_no = t.ticket_no AND bp.flight_id = f.flight_id
            WHERE 
                t.passenger_id = ?
            """
            # logger.info(f"执行SQL查询: {query}")
            cursor.execute(query, (passenger_id,))
            
            rows = cursor.fetchall()
            logger.info(f"查询结果行数: {len(rows)}")
            
            column_names = [column[0] for column in cursor.description]
            results = [dict(zip(column_names, row)) for row in rows]
            return results
            
    except sqlite3.Error as e:
        logger.error(f"数据库查询错误: {str(e)}")
        raise


@tool
def search_flights(
    departure_airport: Optional[str] = None,
    arrival_airport: Optional[str] = None,
    start_time: Optional[date | datetime] = None,
    end_time: Optional[date | datetime] = None,
    limit: int = 20,
) -> list[dict]:
    """Search for flights based on departure airport, arrival airport, and departure time range."""
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    query = "SELECT * FROM flights WHERE 1 = 1"
    params = []

    if departure_airport:
        query += " AND departure_airport = ?"
        params.append(departure_airport)

    if arrival_airport:
        query += " AND arrival_airport = ?"
        params.append(arrival_airport)

    if start_time:
        query += " AND scheduled_departure >= ?"
        params.append(start_time)

    if end_time:
        query += " AND scheduled_departure <= ?"
        params.append(end_time)
    query += " LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    column_names = [column[0] for column in cursor.description]
    results = [dict(zip(column_names, row)) for row in rows]

    cursor.close()
    conn.close()

    return results


@tool
def update_ticket_to_new_flight(
    ticket_no: str, new_flight_id: int, *, config: RunnableConfig
) -> str:
    """Update the user's ticket to a new valid flight."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError(ERROR_NO_PASSENGER_ID)

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT departure_airport, arrival_airport, scheduled_departure FROM flights WHERE flight_id = ?",
        (new_flight_id,),
    )
    new_flight = cursor.fetchone()
    if not new_flight:
        cursor.close()
        conn.close()
        return "Invalid new flight ID provided."
    column_names = [column[0] for column in cursor.description]
    new_flight_dict = dict(zip(column_names, new_flight))
    timezone = pytz.timezone("Etc/GMT-3")
    current_time = datetime.now(tz=timezone)
    departure_time = datetime.strptime(
        new_flight_dict["scheduled_departure"], "%Y-%m-%d %H:%M:%S.%f%z"
    )
    time_until = (departure_time - current_time).total_seconds()
    if time_until < (3 * 3600):
        return f"Not permitted to reschedule to a flight that is less than 3 hours from the current time. Selected flight is at {departure_time}."

    cursor.execute(
        "SELECT flight_id FROM ticket_flights WHERE ticket_no = ?", (ticket_no,)
    )
    current_flight = cursor.fetchone()
    if not current_flight:
        cursor.close()
        conn.close()
        return "No existing ticket found for the given ticket number."

    # Check the signed-in user actually has this ticket
    cursor.execute(
        "SELECT * FROM tickets WHERE ticket_no = ? AND passenger_id = ?",
        (ticket_no, passenger_id),
    )
    current_ticket = cursor.fetchone()
    if not current_ticket:
        cursor.close()
        conn.close()
        return f"Current signed-in passenger with ID {passenger_id} not the owner of ticket {ticket_no}"

    # In a real application, you'd likely add additional checks here to enforce business logic,
    # like "does the new departure airport match the current ticket", etc.
    # While it's best to try to be *proactive* in 'type-hinting' policies to the LLM
    # it's inevitably going to get things wrong, so you **also** need to ensure your
    # API enforces valid behavior
    cursor.execute(
        "UPDATE ticket_flights SET flight_id = ? WHERE ticket_no = ?",
        (new_flight_id, ticket_no),
    )
    conn.commit()

    cursor.close()
    conn.close()
    return "Ticket successfully updated to new flight."


@tool
def cancel_ticket(ticket_no: str, *, config: RunnableConfig) -> str:
    """Cancel the user's ticket and remove it from the database."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError(ERROR_NO_PASSENGER_ID)
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT flight_id FROM ticket_flights WHERE ticket_no = ?", (ticket_no,)
    )
    existing_ticket = cursor.fetchone()
    if not existing_ticket:
        cursor.close()
        conn.close()
        return "No existing ticket found for the given ticket number."

    # Check the signed-in user actually has this ticket
    cursor.execute(
        "SELECT ticket_no FROM tickets WHERE ticket_no = ? AND passenger_id = ?",
        (ticket_no, passenger_id),
    )
    current_ticket = cursor.fetchone()
    if not current_ticket:
        cursor.close()
        conn.close()
        return f"Current signed-in passenger with ID {passenger_id} not the owner of ticket {ticket_no}"

    cursor.execute("DELETE FROM ticket_flights WHERE ticket_no = ?", (ticket_no,))
    conn.commit()

    cursor.close()
    conn.close()
    return "Ticket successfully cancelled."