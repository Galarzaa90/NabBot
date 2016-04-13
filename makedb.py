import sqlite3
import sys

#Get a database connection object
conn = sqlite3.connect('users.db')
c = conn.cursor()

#If this is run with 'force' as a parameter, it drops all the tables and then creates them again
if('force' in sys.argv):
    c.execute("DROP TABLE IF EXISTS discordUsers")
    c.execute("DROP TABLE IF EXISTS tibiaChars")
    
#Create the table if they don't exist already
c.execute("CREATE TABLE IF NOT EXISTS discordUsers(id INT, weight INT)")
c.execute("CREATE TABLE IF NOT EXISTS tibiaChars(discordUser INT, charName TEXT)")
    
conn.commit()
conn.close()
