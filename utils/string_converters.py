import re


def to_camel_case(s: str)->str:
    """
    Convert a lowercase, underscore-separated string to CamelCase.
    """
    return ''.join(word.capitalize() for word in s.split('_'))

def to_camel_case_with_spaces(s: str) -> str:
    """
    Convert a lowercase, underscore-separated string to Camel Case with spaces.
    """
    return ' '.join(word.capitalize() for word in s.split('_'))


def validate_name(model_name):
    """
    Validate the model name:
    - Must be lowercase
    - Must not contain spaces
    - Must only contain letters, numbers, and underscores

    :param model_name: The name of the model
    :raises ValueError: If the model name is invalid
    """
    if not re.match(r"^[a-z_]+$", model_name):
        raise ValueError(f"Invalid name '{model_name}'. Model names must be lowercase, "
                         f"contain only letters and underscores, and must not have spaces.")