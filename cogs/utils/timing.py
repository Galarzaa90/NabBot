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

import datetime as dt
import time
from calendar import timegm
from typing import Union

from cogs.utils import join_list


class HumanDelta:
    """Represent time in a natural way."""
    time_attributes = ("years", "months", "days", "hours", "minutes", "seconds")
    short_attributes = ("y", "mo", "d", "h", "m", "s")

    def __init__(self, delta, duration=False):
        if not isinstance(delta, dt.timedelta):
            raise ValueError("Parameter is not a datetime.timedelta instance.")
        self.negative = delta.total_seconds() < 0
        delta = abs(delta)
        self.duration = duration
        self.hours, remainder = divmod(int(delta.total_seconds()), 3600)
        self.minutes, self.seconds = divmod(remainder, 60)
        self.days, self.hours = divmod(self.hours, 24)
        self.years, self.days = divmod(self.days, 365)
        self.months, self.days = divmod(self.days, 30)

    def long(self, max_attributes=0):
        if not max_attributes:
            max_attributes = len(self.time_attributes)
        output = []
        for attr in self.time_attributes:
            elem = getattr(self, attr)
            if not elem:
                continue

            if elem > 1:
                output.append(f'{elem} {attr}')
            else:
                output.append(f'{elem} {attr[:-1]}')

        if not output:
            return "now"
        content = join_list(output[:min(max_attributes, len(output))])
        if not self.duration:
            if self.negative:
                content += " ago"
            else:
                content = "in " + content
        return content

    def short(self, max_attributes=0):
        if not max_attributes:
            max_attributes = len(self.time_attributes)
        output = []
        for attr, short in zip(self.time_attributes, self.short_attributes):
            elem = getattr(self, attr)
            if not elem:
                continue

            output.append(f'{elem}{short}')

        if not output:
            return "now"
        content = " ".join(output[:min(max_attributes, len(output))])
        if not self.duration:
            if self.negative:
                content += " ago"
            else:
                content = "in " + content
        return content

    @classmethod
    def from_seconds(cls, seconds: Union[int, float], duration=False):
        return cls(dt.timedelta(seconds=seconds), duration)

    @classmethod
    def from_date(cls, date: dt.datetime, source=None):
        if source is None:
            source = dt.datetime.now(tz=date.tzinfo)
        return cls(date-source)

    def __repr__(self):
        attrs = []
        for att in self.time_attributes:
            value = getattr(self, att, 0)
            if value:
                attrs.append(f"{att}={value}")
        sign = "-" if self.negative else ""
        return f"{sign}<{self.__class__.__name__ } {', '.join(attrs)}>"


def get_local_timezone() -> int:
    """Returns the server's local time zone

    :return: The UTC offset of the host's timezone.
    """
    # Getting local time and GMT
    t = time.localtime()
    u = time.gmtime(time.mktime(t))
    # UTC Offset
    return (timegm(t) - timegm(u)) / 60 / 60
