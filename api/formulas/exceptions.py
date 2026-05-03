"""
Custom exceptions for the formulas module.

This module defines custom exception classes for formula validation
and evaluation errors.
"""


class FormulaError(Exception):
    """Base exception for all formula-related errors."""
    pass


class FormulaValidationError(FormulaError):
    """Raised when formula validation fails."""
    
    def __init__(self, message: str, field_name: str = None, formula: str = None):
        """
        Initialize the validation error.
        
        Args:
            message: Error message
            field_name: Name of the field where validation failed
            formula: The formula that failed validation
        """
        self.field_name = field_name
        self.formula = formula
        super().__init__(message)
    
    def __str__(self) -> str:
        msg = super().__str__()
        if self.field_name:
            msg = f"Field '{self.field_name}': {msg}"
        if self.formula:
            msg = f"{msg} (formula: {self.formula})"
        return msg


class FormulaEvaluationError(FormulaError):
    """Raised when formula evaluation fails."""
    
    def __init__(self, message: str, function_name: str = None, parameters: list = None):
        """
        Initialize the evaluation error.
        
        Args:
            message: Error message
            function_name: Name of the function that failed
            parameters: Parameters passed to the function
        """
        self.function_name = function_name
        self.parameters = parameters
        super().__init__(message)
    
    def __str__(self) -> str:
        msg = super().__str__()
        if self.function_name:
            msg = f"Function '{self.function_name}': {msg}"
        if self.parameters:
            msg = f"{msg} (parameters: {self.parameters})"
        return msg


class InvalidFunctionError(FormulaError):
    """Raised when an invalid or unsupported function is used."""
    pass


class InvalidParameterError(FormulaError):
    """Raised when invalid parameters are provided to a function."""
    pass


class TypeMismatchError(FormulaError):
    """Raised when there's a type mismatch in formula evaluation."""
    
    def __init__(self, message: str, expected_type: str = None, actual_type: str = None):
        """
        Initialize the type mismatch error.
        
        Args:
            message: Error message
            expected_type: The expected data type
            actual_type: The actual data type received
        """
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(message)
    
    def __str__(self) -> str:
        msg = super().__str__()
        if self.expected_type and self.actual_type:
            msg = f"{msg} (expected: {self.expected_type}, got: {self.actual_type})"
        return msg


class RecursionLimitError(FormulaError):
    """Raised when formula recursion limit is exceeded."""
    pass
