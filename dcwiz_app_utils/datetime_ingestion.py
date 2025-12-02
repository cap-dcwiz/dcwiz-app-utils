from datetime import timezone, timedelta, datetime, UTC
from typing import Optional, Annotated, Union
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, BeforeValidator, model_validator

from dcwiz_app_utils.error import ErrorCode


def validate_and_convert_to_utc(v: Union[str, datetime, int, None]) -> Optional[datetime]:
    """
    Universal timestamp validator - converts any input to UTC datetime.
    Accepts: ISO strings, datetime objects, Unix timestamps (seconds or milliseconds)
    """
    if v is None:
        return None

    # Handle datetime objects
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    # Handle Unix timestamps
    if isinstance(v, (int, float)):
        if v > 4102444800:  # Assume milliseconds if > year 2100 in seconds
            v = v / 1000
        return datetime.fromtimestamp(v, tz=timezone.utc)

    # Handle string inputs
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            try:
                timestamp = float(v)
                if timestamp > 4102444800:
                    timestamp = timestamp / 1000
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)
            except ValueError:
                raise ValueError(
                    f"Invalid timestamp format: {v}. "
                    "Expected ISO format, datetime object, or Unix timestamp"
                )

    raise ValueError(f"Unsupported timestamp type: {type(v)}")


# Type alias for automatically validated UTC timestamps
UTCDatetime = Annotated[datetime, BeforeValidator(validate_and_convert_to_utc)]

class TimezoneMixin(BaseModel):
    """
    Mixin for query params that need timezone output conversion.
    Add this to format results in user's local timezone.
    """
    tz: Optional[str] = Field(
        None,
        description="Output timezone - IANA string (e.g., 'America/New_York') or UTC offset in minutes (e.g., -480)",
        examples=["America/New_York", "Asia/Singapore", "-480", "480"]
    )

    def get_output_timezone(self) -> timezone:
        """Get the output timezone, defaulting to UTC."""
        if self.tz is None:
            return UTC

        # Handle numeric offset (minutes)
        try:
            offset_minutes = int(self.tz)
            hours = offset_minutes // 60
            minutes = abs(offset_minutes) % 60
            return timezone(timedelta(hours=hours, minutes=minutes))
        except ValueError:
            # Handle IANA timezone string - convert ZoneInfo to timezone
            zone = ZoneInfo(self.tz)
            # Get the current UTC offset from the ZoneInfo
            offset = datetime.now(zone).utcoffset()
            if offset is None:
                return UTC
            return timezone(offset)

    def to_output_tz(self, dt: datetime) -> datetime:
        """Convert a UTC datetime to the output timezone."""
        return dt.astimezone(self.get_output_timezone())

    def format_datetime(self, dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Format a datetime in the output timezone."""
        return self.to_output_tz(dt).strftime(fmt)


class TimeRangeMixin(BaseModel):
    """
    Mixin for query params that need time range filtering with automatic UTC conversion.
    Add this to any param schema that needs start/end datetime filtering.
    """
    start: UTCDatetime = Field(..., description="Start datetime (converted to UTC)")
    end: UTCDatetime = Field(..., description="End datetime (converted to UTC)")

    @model_validator(mode='after')
    def validate_end_after_start(self):
        """Ensure end is after start."""
        if self.start and self.end <= self.start:
            raise ValueError(ErrorCode.ERR_TIME_RANGE_ERROR.value)
        return self

    def is_within_range(self, dt: datetime) -> bool:
        """Check if a datetime falls within the range."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return self.start <= dt < self.end
