from discord.ext import commands


class NabError(Exception):
    """Base exception for all NabBot related errors."""
    pass


class CannotEmbed(commands.CheckFailure, NabError):
    pass


class NetworkError(NabError):
    """Exception raised when a network call fails after the set reattempts."""
    pass


class CannotPaginate(NabError):
    """Exception raised when a context doesn't meet all the requirements for pagination."""
    pass
