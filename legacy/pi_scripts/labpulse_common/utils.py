from datetime import datetime


def get_timestamp():
    """Returns a standardized canonical timestamp string."""
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")
