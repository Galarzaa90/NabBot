import sqlite3
import sys

#Get a database connection object
conn = sqlite3.connect('users.db')
c = conn.cursor()

#If this is run with 'force' as a parameter, it drops all the tables and then creates them again
if('force' in sys.argv):
    c.execute("DROP TABLE IF EXISTS discord_users")
    c.execute("DROP TABLE IF EXISTS chars")
    c.execute("DROP TABLE IF EXISTS char_levelups")
    
#Create the table if they don't exist already
c.execute("""CREATE TABLE discord_users (
        id	INTEGER NOT NULL,
        weight	INTEGER DEFAULT 5,
        PRIMARY KEY(id)
        )""")
c.execute("""CREATE TABLE chars (
        id	INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id	INTEGER,
        name	TEXT,
        last_level	INTEGER DEFAULT -1,
        last_death_time	TEXT
        )""")
c.execute("""CREATE TABLE char_levelups (
        char_id	INTEGER,
        level	INTEGER,
        date	INTEGER
        )""")
    
conn.commit()
conn.close()
