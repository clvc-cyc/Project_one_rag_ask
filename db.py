import sqlite3  #轻量级、嵌入式关系数据库




def init_db():
    conn = sqlite3.connect("chat.db")


    cursor=conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS message(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant TEXT,
            session_id TEXT,
            role TEXT,
            context TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
     )
    ''')
    conn.close()

def save_message(tenant:str,session_id:str,role:str,context:str):
    conn=sqlite3.connect("chat.db")
    cursor=conn.cursor()
    cursor.execute(
        "INSERT INTO message (tenant,session_id,role,context) VALUES(?,?,?,?)",
        (tenant,session_id,role,context)
    )
    conn.commit()
    conn.close()

def get_history(tenant:str,session_id:str,limit:int=5):
    conn=sqlite3.connect("chat.db")
    cursor=conn.cursor()
    cursor.execute("SELECT role,context FROM message WHERE session_id=? and tenant=? "
                   "ORDER BY ID DESC LIMIT ?",(session_id,tenant,limit))
    rows=cursor.fetchall()
    history=[]
    for role,context in rows:
        history.append((role,context))
    history=history[::-1]
    conn.close()
    return history


