# src/utils/datetime_utilities.py

import pendulum


class DateTimeUtility:
    """
    A robust utility class for timestamp-related operations using Pendulum.
    """

    # Default timezone for operations
    default_timezone = "UTC"

    # Custom formats registry
    custom_formats = {}

    # Cached current timestamp
    _cached_now = None

    @staticmethod
    def get_current_timestamp(refresh=False):
        """
        Returns the current timestamp, optionally refreshing the cached value.

        Args:
            refresh (bool): If True, refreshes the cached timestamp.

        Returns:
            pendulum.DateTime: The current timestamp.
        """
        if not DateTimeUtility._cached_now or refresh:
            DateTimeUtility._cached_now = pendulum.now(tz=DateTimeUtility.default_timezone)
        return DateTimeUtility._cached_now

    @staticmethod
    def format_timestamp(timestamp=None, fmt="YYYY-MM-DD HH:mm:ss"):
        """
        Formats a given timestamp. Defaults to the current timestamp.

        Args:
            timestamp (pendulum.DateTime, optional): The timestamp to format.
            fmt (str): The format string.

        Returns:
            str: The formatted timestamp as a string.
        """
        if timestamp is None:
            timestamp = DateTimeUtility.get_current_timestamp()
        try:
            formatted = timestamp.format(fmt)
            return formatted
        except Exception as e:
            raise ValueError(f"Failed to format timestamp with format '{fmt}': {e}")

    @staticmethod
    def parse_timestamp(timestamp_str, fmt="YYYY-MM-DD HH:mm:ss"):
        """
        Parses a string into a Pendulum timestamp.

        Args:
            timestamp_str (str): The timestamp string to parse.
            fmt (str): The format string.

        Returns:
            pendulum.DateTime: The parsed timestamp.
        """
        try:
            return pendulum.from_format(timestamp_str, fmt, tz=DateTimeUtility.default_timezone)
        except Exception as e:
            raise ValueError(f"Invalid timestamp '{timestamp_str}' with format '{fmt}': {e}")

    @staticmethod
    def to_iso8601(timestamp=None):
        """
        Converts a given timestamp to ISO 8601 format.

        Args:
            timestamp (pendulum.DateTime, optional): The timestamp to format. Defaults to current timestamp.

        Returns:
            str: The ISO 8601 formatted timestamp.
        """
        if timestamp is None:
            timestamp = DateTimeUtility.get_current_timestamp()
        return timestamp.to_iso8601_string()

    @staticmethod
    def format_localized(timestamp=None, locale="en"):
        """
        Formats a timestamp with a localized format.

        Args:
            timestamp (pendulum.DateTime, optional): The timestamp to format. Defaults to current timestamp.
            locale (str): The locale for formatting (e.g., 'en', 'fr').

        Returns:
            str: The localized formatted timestamp.
        """
        if timestamp is None:
            timestamp = DateTimeUtility.get_current_timestamp()
        return timestamp.format("LLLL", locale=locale)

    @staticmethod
    def calculate_elapsed_time(start_time, end_time=None):
        """
        Calculates the elapsed time between two timestamps.

        Args:
            start_time (pendulum.DateTime): The starting timestamp.
            end_time (pendulum.DateTime, optional): The ending timestamp. Defaults to now.

        Returns:
            pendulum.Duration: The duration between the timestamps.
        """
        if end_time is None:
            end_time = DateTimeUtility.get_current_timestamp()
        return end_time - start_time

    @staticmethod
    def add_time_delta(timestamp=None, days=0, hours=0, minutes=0, seconds=0):
        """
        Adds a time delta to a given timestamp.

        Args:
            timestamp (pendulum.DateTime, optional): The base timestamp. Defaults to current timestamp.
            days (int): Number of days to add.
            hours (int): Number of hours to add.
            minutes (int): Number of minutes to add.
            seconds (int): Number of seconds to add.

        Returns:
            pendulum.DateTime: The resulting timestamp after adding the delta.
        """
        if timestamp is None:
            timestamp = DateTimeUtility.get_current_timestamp()
        return timestamp.add(days=days, hours=hours, minutes=minutes, seconds=seconds)

    @staticmethod
    def register_custom_format(name, format_string):
        """
        Registers a custom format in the utility.

        Args:
            name (str): The name of the custom format.
            format_string (str): The format string.
        """
        DateTimeUtility.custom_formats[name] = format_string

    @staticmethod
    def format_with_custom(timestamp=None, format_name=None):
        """
        Formats a timestamp using a registered custom format.

        Args:
            timestamp (pendulum.DateTime, optional): The timestamp to format. Defaults to current timestamp.
            format_name (str): The name of the custom format.

        Returns:
            str: The formatted timestamp.
        """
        if timestamp is None:
            timestamp = DateTimeUtility.get_current_timestamp()
        fmt = DateTimeUtility.custom_formats.get(format_name)
        if not fmt:
            raise ValueError(f"Custom format '{format_name}' not found.")
        return timestamp.format(fmt)
