import sqlite3

# get a database connection object
my_test_dbconn = sqlite3.connect('users.db')
my_test_db = my_test_dbconn.cursor()


# code to create the database table
_create_sql = """\
DROP TABLE IF EXISTS discordUsers;
DROP TABLE IF EXISTS tibiaChars;
CREATE TABLE discordUsers (
   id INTEGER NOT NULL DEFAULT 0,
   weight INTEGER NOT NULL DEFAULT 5,
   UNIQUE(value)
   
CREATE TABLE tibiaChars (
   discordUser INTEGER NOT NULL DEFAULT 0,
   charName TEXT NOT NULL DEFAULT '',
   UNIQUE(value)
);"""

# create the table, dropping any previous table of same name
my_test_db.execute("CREATE TABLE discordUsers(id INT, weight INT)")
my_test_db.execute("CREATE TABLE tibiaChars(discordUser INT, charName TEXT)")
my_test_dbconn.commit()
my_test_dbconn.close()
