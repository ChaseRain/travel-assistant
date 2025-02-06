from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
import sqlite3
from pathlib import Path

def test_database_connection():
    connection = None
    try:
        # 创建数据库引擎
        engine = create_engine(settings.DATABASE_URL)
        # 尝试连接
        connection = engine.connect()
        print("数据库连接成功！")
        return True
    except SQLAlchemyError as e:
        print(f"数据库连接失败：{str(e)}")
        return False
    finally:
        if connection:
            connection.close()

def test_database_tables():
    # 获取数据库文件的绝对路径
    db_path = str(Path(settings.DATABASE_URL.replace('sqlite:///', '')).resolve())
    
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print("\n现有的表：")
        for table in tables:
            print(f"- {table[0]}")
            
        # 检查具体的表结构（以 flights 表为例）
        print("\n检查 flights 表结构：")
        cursor.execute("PRAGMA table_info(flights);")
        columns = cursor.fetchall()
        for col in columns:
            print(f"- {col[1]} ({col[2]})")
            
        # 查看表中的数据量
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"\n{table[0]} 表中有 {count} 条记录")
            
        # 可选：显示一些示例数据
        print("\nflights 表的前3条记录：")
        cursor.execute("SELECT * FROM flights LIMIT 3")
        rows = cursor.fetchall()
        for row in rows:
            print(row)
            
    except sqlite3.Error as e:
        print(f"数据库操作出错：{str(e)}")
    finally:
        if conn:
            conn.close()

def test_flight_query():
    # 获取数据库文件的绝对路径
    db_path = str(Path(settings.DATABASE_URL.replace('sqlite:///', '')).resolve())
    
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 执行复杂查询
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
            JOIN boarding_passes bp ON bp.ticket_no = t.ticket_no 
                AND bp.flight_id = f.flight_id
        WHERE 
            t.passenger_id = ?
        """
        
        cursor.execute(query, ('0817 363231',))
        rows = cursor.fetchall()
        
        # 获取列名
        column_names = [description[0] for description in cursor.description]
        
        # 打印列名
        print("\n查询结果的列名：")
        print(column_names)
        
        # 打印结果
        print("\n查询结果：")
        for row in rows:
            result_dict = dict(zip(column_names, row))
            print(result_dict)
            
    except sqlite3.Error as e:
        print(f"数据库查询出错：{str(e)}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    test_database_connection()
    test_database_tables()
    test_flight_query() 