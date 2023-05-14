import sqlite3

class SQLiteConnector:
    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect("database_project.db")

    def execute(self, query, params=None):
        self.connect()
        cursor = self.conn.cursor()
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
    
        if query.lower().startswith("insert") or  query.lower().startswith("update"):
            self.conn.commit()
            last_row_id = cursor.lastrowid
            self.conn.close()
            return last_row_id

        result = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in result]

        self.conn.close()

        return rows    