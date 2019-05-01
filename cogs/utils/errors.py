#  Copyright 2019 Allan Galarza
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from discord.ext import commands


class NabError(Exception):
    """Base exception for all NabBot related errors."""
    pass


class UnathorizedUser(commands.CheckFailure, NabError):
    pass


class CannotEmbed(commands.CheckFailure, NabError):
    pass


class NetworkError(NabError):
    """Exception raised when a network call fails after the set reattempts."""
    pass


class CannotPaginate(NabError):
    """Exception raised when a context doesn't meet all the requirements for pagination."""
    pass


class NotTracking(NabError, commands.CheckFailure):
    """Exception raised when a command is used from a server that is not tracking any worlds."""
    pass
