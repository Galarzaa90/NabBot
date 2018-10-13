import asyncio
import json
import os

import asyncpg
import click

from cogs.utils.database_migration import check_database, import_legacy_db
from nabbot import NabBot


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

    pool = await asyncpg.create_pool(uri, init=init, **kwargs)
    return pool


def run_bot():
    loop = asyncio.get_event_loop()

    try:
        pool = loop.run_until_complete(create_pool(get_uri(), command_timeout=60))  # type: asyncpg.pool.Pool
    except Exception:
        print('Could not set up PostgreSQL. Exiting.')
        return

    loop.run_until_complete(check_database(pool))

    bot = NabBot()
    bot.pool = pool
    bot.run()


@click.group(invoke_without_command=True, options_metavar='[options]')
@click.pass_context
def main(ctx):
    """Launches the bot."""
    if ctx.invoked_subcommand is None:
        run_bot()

@main.command()
@click.option('-path', '--path', help="Name for the database file.", default="data/users.db")
def migrate(path):
    loop = asyncio.get_event_loop()
    try:
        pool = loop.run_until_complete(create_pool(get_uri(), command_timeout=60))  # type: asyncpg.pool.Pool
    except Exception:
        print('Could not set up PostgreSQL. Exiting.')
        return

    loop.run_until_complete(check_database(pool))
    loop.run_until_complete(import_legacy_db(pool, path))


if __name__ == "__main__":
    main()
