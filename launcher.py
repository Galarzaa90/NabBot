import asyncio
import json
import logging
import os
from logging.handlers import TimedRotatingFileHandler

import asyncpg
import click

from cogs.utils.database_migration import check_database, import_legacy_db, drop_tables
from nabbot import NabBot

# Logging optimization
logging.logThreads = 0
logging.logProcesses = 0
logging._srcfile = None
logging_formatter = logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s')
# Save log to file (info level)
file_handler = TimedRotatingFileHandler('logs/nabbot', when='midnight')
file_handler.suffix = "%Y_%m_%d.log"
file_handler.setFormatter(logging_formatter)
# Print output to console too (debug level)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging_formatter)

# NabBot log
log = logging.getLogger("nabbot")
log.setLevel(logging.INFO)
log.addHandler(file_handler)
log.addHandler(console_handler)


def get_uri():
    """When the bot is run without a login.py file, it prompts the user for login info"""
    file_name = "postgresql.txt"
    try:
        if not os.path.isfile(file_name):
            print("No PostgreSQL URI has been set.")
            host = input("Server address [localhost]:")
            if not host:
                host = "localhost"
            user = input("Username:")
            password = input("Password:")
            database = input("Database name [nabbot]:")
            if not database:
                database = "nabbot"
            uri = f"postgresql://{user}:{password}@{host}/{database}"
            with open(file_name, "w+") as f:
                f.write(uri)
            print("PostgreSQL has been saved to postgresql.txt, you can edit this file later to change it.")
            input("Press any key to continue...")
            return uri
        else:
            with open(file_name) as f:
                return f.read()
    except KeyboardInterrupt:
        exit()


async def create_pool(uri, **kwargs) -> asyncpg.pool.Pool:
    def _encode_jsonb(value):
        return json.dumps(value)

    def _decode_jsonb(value):
        return json.loads(value)

    async def init(con):
        await con.set_type_codec('jsonb', schema='pg_catalog', encoder=_encode_jsonb, decoder=_decode_jsonb,
                                 format='text')
    try:
        pool = await asyncpg.create_pool(uri, init=init, **kwargs)
    except ValueError:
        log.error("PostgreSQL error: Invalid URI, check postgresql.txt. "
                  "Format must be 'postresql://user:password@host/database'")
    except asyncpg.PostgresError as e:
        log.error(f"PostgreSQL error: {e}")
    except TimeoutError:
        log.error("PostgreSQL error: Connection timed out.")
    except Exception as e:
        log.error(f"Unexpected error: {e.__class__.__name__}: {e}")
    else:
        return pool


def run_bot():
    log.info("Launching bot...")
    loop = asyncio.get_event_loop()

    pool: asyncpg.pool.Pool = loop.run_until_complete(create_pool(get_uri(), command_timeout=60))
    if pool is None:
        log.error('Could not set up PostgreSQL. Exiting.')
        return

    result = loop.run_until_complete(check_database(pool))
    if not result:
        log.error('Failed to check database')
        return

    bot = NabBot()
    bot.pool = pool
    bot.run()


@click.group(invoke_without_command=True, options_metavar='[options]')
@click.option('--debug/--no-debug', default=False)
@click.pass_context
def main(ctx, debug):
    """Launches the bot."""
    if debug:
        log.setLevel(logging.DEBUG)
    if ctx.invoked_subcommand is None:
        run_bot()


@main.command()
@click.option('-path', '--path', help="Name for the database file.", default="data/users.db")
def migrate(path):
    """Migrates a v1.x.x SQLite to a PostgreSQL database.

    This is a time consuming operation and caution must be taken.
    The original SQLite file is not affected.

    Some checks are performed to avoid duplicates, but migrating more than one database may have unintended effects."""
    log.info("Starting migration")
    loop = asyncio.get_event_loop()
    pool: asyncpg.pool.Pool = loop.run_until_complete(create_pool(get_uri(), command_timeout=60))
    if pool is None:
        log.error('Could not set up PostgreSQL. Exiting.')
        return

    result = loop.run_until_complete(check_database(pool))
    if not result:
        log.error('Failed to check database')
        return

    loop.run_until_complete(import_legacy_db(pool, path))


@main.command()
def empty():
    """Empties out the database.

    Drops all tables from the saved PostgreSQL database.
    This action is irreversible, so use with caution."""
    confirm = click.confirm("Are you sure you want to drop all tables? This action is irreversible.")
    if not confirm:
        click.echo("Operation aborted.")

    loop = asyncio.get_event_loop()
    pool: asyncpg.pool.Pool = loop.run_until_complete(create_pool(get_uri(), command_timeout=60))
    if pool is None:
        log.error('Could not set up PostgreSQL. Exiting.')
        return
    click.echo("Clearing database...")
    loop.run_until_complete(drop_tables(pool))
    click.echo("Done!")


if __name__ == "__main__":
    main()
