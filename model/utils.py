from astropy import units as u
from astropy.time import Time


def time_to_epoch(time: Time) -> u.Quantity:
    """Convert an astropy Time object to an epoch (Julian date)."""
    return time.jd * u.day
