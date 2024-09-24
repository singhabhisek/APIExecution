import sqlite3

def init_db():
    conn = sqlite3.connect('user_access.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_access (
            user_id TEXT PRIMARY KEY,
            access_level TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def insert_user(userid, accesslevel):
    conn = sqlite3.connect('user_access.db')  # Replace with your actual database file
    cursor = conn.cursor()

    try:
        cursor.execute('''
        INSERT INTO user_access (user_id, access_level) VALUES (?, ?)
        ''', (userid, accesslevel))

        conn.commit()
        print(f"User {userid} inserted successfully with access level {accesslevel}.")
    except sqlite3.IntegrityError:
        print(f"User {userid} already exists.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        conn.close()


# Call the function when your app starts
# init_db()

# Example usage
insert_user('AS', 'admin')
insert_user('user456', 'user')
