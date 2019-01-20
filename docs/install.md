# Installation Guide

!!! info
    This information is only for users hosting NabBot on their own.
    If you just invited NabBot to your server, you don't need to read this.

## Installing requirements
In order to run NabBot, you need to install two things: [git](https://git-scm.com/) and [Python 3.6](https://www.python.org/).

When installing on Windows, make sure that you select the option to add Python to `PATH`.

Once installed, you need to find what's the python's executable name, depending on the installation, it can be either `python`, `python3` or `py`.

Once the correct command has been found, open a terminal window on NabBot's root directory and run the following:

```shell
python -m pip install -U -r requirements.txt
```

## Installing PostgreSQL
Since v2.0.0, NabBot uses PostgreSQL instead of SQLite for data storage. This means you must be running a [PostgreSQL](https://www.postgresql.org/) service.
It is recommended to run it on the same machine.

Once it is installed and running, you must create a database and users for NabBot.
You can use the default `root` user, but this is not recommended.

You can create them using any tool you want. Here's an example using `psql`:

```sql
CREATE ROLE nabbot WITH LOGIN PASSWORD 'hunter2';
CREATE DATABASE nabbot OWNER nabbot;
``` 

## Creating an Application
In order to run a Discord bot, you need to create a new application.

1. Go to [My Apps](https://discordapp.com/developers/applications/me) in the developers portal.
2. Once you're here, click on the **New App** button.
3. Fill the fields, Click on **Create App** once you're done.
4. Now that you have created your App, look for the **Create a Bot User** button.
5. You're going to need two things from here, your **Client ID**, found at the top, and your **Token**, found in the Bot section.  
    Your Client ID should look like `391624006744145920` and your token like `MzkxNjI0MDA2NzQ0MTQ1OTIw.DRbYSQ.EbWIRWMqEQCYSBhlnNpG7FQLwZs`

!!! warning
    Your token is secret, never expose it to anyone. Anyone with access to your token can run a bot as you,
    compromising your account if they break discord's Terms of Service

## Running your bot
To run your but, you need to execute `launcher.py`.
The first time you run NabBot, you will be asked for your connection credentials to PostgreSQL.
Here's where you will provide the information created early.

After that, you will be asked for your token. Here's where you will use the token given on the App page.

Once you entered the token, the bot will log in. You should see a dialog showing that the bot is now online.

## Migrating from v1.x.x
If you were running a previous version of NabBot before and you want to migrate your data, you need to run the migrate console command.

```cmd
python launcher.py migrate
```

By default, it will look for the database in the path `data/users.db`, but you can provide a different path using the `--path` argument:

```cmd
python launcher.py migrate --path data/database-backup.db
```

Depending on the size of your previous database, this may take a couple minutes.

!!! warning
    Doing this will delete all the data currently found in your **PostgreSQL** database.  
    Your **SQLite** data will be unaffected by this operation.

## Inviting your bot
To invite your bot to your server, you need to use the authentication URL. Here's where your **Client ID** is used.

```ruby
https://discordapp.com/oauth2/authorize?scope=bot&permissions=268954832&client_id=CLIENT_ID_HERE
```

!!! info
    Make sure you don't deny any of the permissions requested as they are necessary for NabBot.
    For detailed explanation on NabBot's permissions, see the [Permissions](permissions.md) section.
    
You should now see your bot online on your server.
Depending on your privacy settings, you (or the owner of the server) should have received a DM by NabBot explaining how to do the inital configuration.

## Initial configuration
In order for the bot to have access to most of its features, you must configure the world the server tracks.

Use the command [settings world](commands/admin.md#settings-world), for example: `/settings world Gladera`. Then the bot will ask for confirmation.
Once accepted, users can start registering their chars using `\im charName`.

By default, events, level ups and deaths announcements are made on the highest channel available for the bot.
In order to customize this, you can use the following commands: `/settings levelschannel`.

The bot usually shortens command replies on public channels to reduce spam a bit.
Commands used via DM display more information.  
Alternatively, you can create a channel named **#ask-nabbot**.
The bot will give longer responses here and it will delete any message that is not a command, leaving this as a channel dedicated to commands.

Additionally, you can create a channel named **#server-log**. Whenever a user registers characters, they will be shown here, along with their levels and guilds.
Other changes are shown here, such as users leaving, getting banned, changing display names and more.

Further customization can be done on a per-server basis by using the command [settings](commands/admin.md#settings).