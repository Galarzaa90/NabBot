import datetime as dt

from cogs.utils import join_list


class HumanDelta:
    """Represent time in a natural way."""
    time_attributes = ("years", "months", "days", "hours", "minutes", "seconds")
    short_attributes = ("y", "mo", "d", "h", "m", "s")

    def __init__(self, delta):
        if not isinstance(delta, dt.timedelta):
            raise ValueError("Parameter is not a datetime.timedelta instance.")
        self.negative = delta.total_seconds() < 0
        delta = abs(delta)

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
        return join_list(output[:min(max_attributes, len(output))])

    def short(self, max_attributes=0):
        if not max_attributes:
            max_attributes = len(self.time_attributes)
        output = []
        for attr, short in zip(self.time_attributes, self.short_attributes):
            elem = getattr(self, attr)
            if not elem:
                continue

            output.append(f'{elem} {short}')

        if not output:
            return "now"
        return " ".join(output[:min(max_attributes, len(output))])

    @classmethod
    def from_seconds(cls, seconds: int):
        return cls(dt.timedelta(seconds=seconds))

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


