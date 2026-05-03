"""
Filter Logic Validator

Validates filter logic expressions like "1 AND (2 OR NOT 3)" against available filter IDs.
Ensures all referenced filter IDs exist and syntax is correct.

Usage:
    from utils.filter_logic_validator import validate_filter_logic
    
    result = validate_filter_logic("1 AND (2 OR NOT 3)", total_filters=3)
    if not result['valid']:
        print(result['error'])
"""

import re
from typing import Dict, List, Set, Tuple, Optional


class FilterLogicValidator:
    """Validates filter logic expressions with proper error messages."""
    
    # Valid operators
    OPERATORS = {'AND', 'OR', 'NOT'}
    
    def __init__(self, logic_string: str, total_filters: int):
        """
        Initialize validator. 
        
        Args:
            logic_string: Filter logic expression (e.g., "1 AND (2 OR NOT 3)")
            total_filters: Total number of available filters
        """
        self. logic_string = logic_string. strip() if logic_string else ""
        self.total_filters = total_filters
        self.valid_ids = set(range(1, total_filters + 1))
        self.errors = []
        self.warnings = []
        
    def validate(self) -> Dict:
        """
        Main validation method. 
        
        Returns:
            {
                'valid': bool,
                'error': str or None,
                'errors': List[str],
                'warnings': List[str],
                'referenced_ids': Set[int],
                'unreferenced_ids': Set[int]
            }
        """
        # Empty logic is valid (defaults to AND all)
        if not self.logic_string:
            return {
                'valid': True,
                'error': None,
                'errors': [],
                'warnings': [],
                'referenced_ids': set(),
                'unreferenced_ids': self.valid_ids
            }
        
        # Check for basic syntax issues
        if not self._check_basic_syntax():
            return self._build_error_response()
        
        # Tokenize
        try:
            tokens = self._tokenize()
        except ValueError as e:
            self.errors.append(str(e))
            return self._build_error_response()
        
        # Validate tokens
        if not self._validate_tokens(tokens):
            return self._build_error_response()
        
        # Check parentheses balance
        if not self._check_parentheses_balance(tokens):
            return self._build_error_response()
        
        # Validate filter IDs
        referenced_ids = self._extract_filter_ids(tokens)
        if not self._validate_filter_ids(referenced_ids):
            return self._build_error_response()
        
        # Check for unreferenced filters
        unreferenced_ids = self. valid_ids - referenced_ids
        if unreferenced_ids: 
            self.warnings.append(
                f"Filter(s) {sorted(unreferenced_ids)} are not used in the logic expression"
            )
        
        # Validate expression structure
        if not self._validate_expression_structure(tokens):
            return self._build_error_response()
        
        return {
            'valid': True,
            'error': None,
            'errors':  [],
            'warnings': self.warnings,
            'referenced_ids': referenced_ids,
            'unreferenced_ids': unreferenced_ids
        }
    
    def _check_basic_syntax(self) -> bool:
        """Check basic syntax issues."""
        # Check for invalid characters
        valid_pattern = r'^[\d\s\(\)ANDORET]+$'
        if not re.match(valid_pattern, self.logic_string. upper()):
            invalid_chars = set(re.findall(r'[^\d\s\(\)ANDORET]', self.logic_string. upper()))
            self.errors.append(f"Invalid characters found: {', '.join(invalid_chars)}")
            return False
        
        # Check for consecutive operators (except NOT)
        if re.search(r'\b(AND|OR)\s+(AND|OR)\b', self.logic_string. upper()):
            self.errors.append("Consecutive operators (AND/OR) are not allowed")
            return False
        
        return True
    
    def _tokenize(self) -> List[str]:
        """
        Tokenize logic string. 
        
        Returns:
            List of tokens:  ['1', 'AND', '(', '2', 'OR', 'NOT', '3', ')']
        """
        # Normalize to uppercase
        normalized = self.logic_string.upper()
        
        # Extract tokens
        pattern = r'(\d+|AND|OR|NOT|\(|\))'
        tokens = re.findall(pattern, normalized)
        
        if not tokens:
            raise ValueError("No valid tokens found in expression")
        
        return tokens
    
    def _validate_tokens(self, tokens: List[str]) -> bool:
        """Validate token sequence."""
        if not tokens:
            self.errors.append("Expression is empty")
            return False
        
        for i, token in enumerate(tokens):
            # Check for valid token types
            if not (token.isdigit() or token in self.OPERATORS or token in '()'):
                self.errors. append(f"Invalid token:  '{token}'")
                return False
            
            # Binary operators (AND, OR) must not be first or last
            if token in ['AND', 'OR']: 
                if i == 0:
                    self.errors.append(f"Expression cannot start with '{token}'")
                    return False
                if i == len(tokens) - 1:
                    self.errors.append(f"Expression cannot end with '{token}'")
                    return False
            
            # Check for double negation patterns
            if token == 'NOT' and i + 1 < len(tokens) and tokens[i + 1] == 'NOT':
                self.warnings.append("Double negation found (NOT NOT), consider simplifying")
        
        return True
    
    def _check_parentheses_balance(self, tokens: List[str]) -> bool:
        """Check if parentheses are balanced."""
        balance = 0
        for token in tokens:
            if token == '(':
                balance += 1
            elif token == ')':
                balance -= 1
            
            if balance < 0:
                self.errors.append("Unmatched closing parenthesis ')'")
                return False
        
        if balance > 0:
            self.errors.append(f"Unmatched opening parenthesis '(' (missing {balance} closing)")
            return False
        
        return True
    
    def _extract_filter_ids(self, tokens: List[str]) -> Set[int]:
        """Extract all filter IDs from tokens."""
        return {int(token) for token in tokens if token.isdigit()}
    
    def _validate_filter_ids(self, referenced_ids:  Set[int]) -> bool:
        """Validate that all referenced filter IDs exist."""
        invalid_ids = referenced_ids - self.valid_ids
        
        if invalid_ids:
            self.errors.append(
                f"Invalid filter ID(s): {sorted(invalid_ids)}. "
                f"Valid range is 1-{self.total_filters}"
            )
            return False
        
        return True
    
    def _validate_expression_structure(self, tokens: List[str]) -> bool:
        """Validate the structure of the expression using recursive descent."""
        try:
            tokens_copy = tokens[:]
            self._parse_expression(tokens_copy)
            
            # If tokens remain, expression is malformed
            if tokens_copy:
                self.errors.append(
                    f"Unexpected tokens after valid expression: {' '.join(tokens_copy)}"
                )
                return False
            
            return True
        except ValueError as e:
            self.errors.append(str(e))
            return False
    
    def _parse_expression(self, tokens: List[str]):
        """Parse OR expression (lowest precedence)."""
        self._parse_term(tokens)
        
        while tokens and tokens[0] == 'OR':
            tokens.pop(0)
            if not tokens or tokens[0] in ['AND', 'OR', ')']:
                raise ValueError("OR operator must be followed by a valid expression")
            self._parse_term(tokens)
    
    def _parse_term(self, tokens: List[str]):
        """Parse AND expression (medium precedence)."""
        self._parse_factor(tokens)
        
        while tokens and tokens[0] == 'AND':
            tokens.pop(0)
            if not tokens or tokens[0] in ['AND', 'OR', ')']:
                raise ValueError("AND operator must be followed by a valid expression")
            self._parse_factor(tokens)
    
    def _parse_factor(self, tokens: List[str]):
        """Parse NOT expression (high precedence)."""
        if tokens and tokens[0] == 'NOT':
            tokens.pop(0)
            if not tokens or tokens[0] in ['AND', 'OR']: 
                raise ValueError("NOT operator must be followed by a valid expression")
            self._parse_factor(tokens)
        else:
            self._parse_atom(tokens)
    
    def _parse_atom(self, tokens: List[str]):
        """Parse number or parenthesized expression."""
        if not tokens:
            raise ValueError("Unexpected end of expression")
        
        token = tokens. pop(0)
        
        if token == '(':
            self._parse_expression(tokens)
            if not tokens or tokens. pop(0) != ')':
                raise ValueError("Missing closing parenthesis")
        elif token. isdigit():
            pass  # Valid filter ID
        else:
            raise ValueError(f"Expected filter ID or '(', got '{token}'")
    
    def _build_error_response(self) -> Dict:
        """Build error response."""
        return {
            'valid': False,
            'error':  self.errors[0] if self.errors else "Unknown validation error",
            'errors': self.errors,
            'warnings':  self.warnings,
            'referenced_ids': set(),
            'unreferenced_ids': set()
        }


def validate_filter_logic(logic_string: str, total_filters: int) -> Dict:
    """
    Convenience function to validate filter logic.
    
    Args:
        logic_string: Filter logic expression
        total_filters: Total number of available filters
        
    Returns: 
        Validation result dictionary
        
    Examples:
        >>> validate_filter_logic("1 AND 2", 2)
        {'valid': True, 'error': None, ... }
        
        >>> validate_filter_logic("1 AND 5", 3)
        {'valid': False, 'error': 'Invalid filter ID(s): [5]... ', ...}
    """
    validator = FilterLogicValidator(logic_string, total_filters)
    return validator.validate()


# Example usage and tests
# if __name__ == "__main__":
#     test_cases = [
#         ("1 AND 2", 2, True),
#         ("1 AND (2 OR 3)", 3, True),
#         ("1 AND (2 OR NOT 3)", 3, True),
#         ("(1 OR 2) AND (3 OR 4)", 4, True),
#         ("NOT 1", 1, True),
#         ("1 AND 5", 3, False),  # Invalid ID
#         ("1 AND AND 2", 2, False),  # Consecutive operators
#         ("AND 1", 2, False),  # Starts with operator
#         ("1 AND", 2, False),  # Ends with operator
#         ("1 AND (2", 2, False),  # Unbalanced parentheses
#         ("1 AND 2)", 2, False),  # Unbalanced parentheses
#         ("", 3, True),  # Empty is valid
#         ("1 AND 2 OR 3", 5, True),  # Unreferenced filters (warning)
#     ]
    
#     print("=" * 60)
#     print("FILTER LOGIC VALIDATOR TESTS")
#     print("=" * 60)
    
#     for logic, total, expected_valid in test_cases:
#         result = validate_filter_logic(logic, total)
#         status = "✓ PASS" if result['valid'] == expected_valid else "✗ FAIL"
        
#         print(f"\n{status}")
#         print(f"  Logic: '{logic}'")
#         print(f"  Total Filters: {total}")
#         print(f"  Valid: {result['valid']}")
        
#         if result['error']:
#             print(f"  Error: {result['error']}")
        
#         if result['warnings']:
#             print(f"  Warnings: {result['warnings']}")
        
#         if result['referenced_ids']:
#             print(f"  Referenced IDs: {sorted(result['referenced_ids'])}")
        
#         if result['unreferenced_ids']:
#             print(f"  Unreferenced IDs: {sorted(result['unreferenced_ids'])}")