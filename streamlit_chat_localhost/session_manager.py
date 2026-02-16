import uuid
from database import get_connection


def create_session(username, name):
    session_id = str(uuid.uuid4())

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO sessions (id, username, name) VALUES (?, ?, ?)",
        (session_id, username, name),
    )

    conn.commit()
    conn.close()

    return session_id


def get_sessions(username):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name FROM sessions WHERE username=? ORDER BY created_at DESC",
        (username,),
    )

    data = cursor.fetchall()
    conn.close()

    return data


def update_session(session_id, name):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE sessions SET name=? WHERE id=?",
        (name, session_id),
    )

    conn.commit()
    conn.close()


def delete_session(session_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM sessions WHERE id=?",
        (session_id,),
    )

    conn.commit()
    conn.close()
