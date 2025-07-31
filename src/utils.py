import re

def get_safe_filename(file_name: str) -> str:
    """Removes special characters from a filename to make it safe for use as an index or table name."""
    base_name = re.sub(r'\.[^.]*$', '', file_name) # Remove extension
    return re.sub(r'[^\w\.-]', '_', base_name)
