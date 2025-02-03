import sqlite3
from typing import List, Dict, Any

class DatabaseService:
    def __init__(self, db_path: str = "travel.db"):
        self.db_path = db_path
        
    def get_connection(self):
        return sqlite3.connect(self.db_path)
        
    def search_flights(self, departure: str, arrival: str) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT * FROM flights 
        WHERE departure_airport = ? 
        AND arrival_airport = ?
        """
        
        cursor.execute(query, (departure, arrival))
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return results 