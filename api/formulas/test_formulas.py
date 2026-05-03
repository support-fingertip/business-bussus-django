"""
Basic tests for formula evaluation and validation.

This module contains unit tests for the formula processing functionality.
"""
import unittest
from datetime import datetime, date
from api.formulas.evaluate_formula import (
    process_formula,
    extract_functions,
    parse_function,
    split_parameters,
    get_value
)
from api.formulas.safe_evaluator import safe_evaluate
from api.formulas.exceptions import (
    FormulaEvaluationError,
    InvalidFunctionError
)


class TestSafeEvaluator(unittest.TestCase):
    """Tests for the safe expression evaluator."""
    
    def test_basic_arithmetic(self):
        """Test basic arithmetic operations."""
        self.assertEqual(safe_evaluate("2 + 3"), 5)
        self.assertEqual(safe_evaluate("10 - 5"), 5)
        self.assertEqual(safe_evaluate("4 * 5"), 20)
        self.assertEqual(safe_evaluate("20 / 4"), 5)
    
    def test_with_context(self):
        """Test evaluation with context variables."""
        context = {"x": 10, "y": 20}
        self.assertEqual(safe_evaluate("x + y", context), 30)
        self.assertEqual(safe_evaluate("x * 2", context), 20)
    
    def test_comparison_operations(self):
        """Test comparison operations."""
        self.assertTrue(safe_evaluate("5 > 3"))
        self.assertFalse(safe_evaluate("5 < 3"))
        self.assertTrue(safe_evaluate("5 == 5"))
    
    def test_invalid_expression(self):
        """Test that invalid expressions raise errors."""
        with self.assertRaises(ValueError):
            safe_evaluate("import os")


class TestExtractFunctions(unittest.TestCase):
    """Tests for function extraction from formulas."""
    
    def test_simple_function(self):
        """Test extraction of a simple function."""
        formula = "SUM(a, b)"
        functions = extract_functions(formula)
        self.assertEqual(len(functions), 1)
        self.assertEqual(functions[0], "SUM(a, b)")
    
    def test_nested_functions(self):
        """Test extraction of nested functions."""
        formula = "SUM(MAX(a, b), MIN(c, d))"
        functions = extract_functions(formula)
        # Should extract the outermost function
        self.assertGreater(len(functions), 0)
    
    def test_no_functions(self):
        """Test formula with no functions."""
        formula = "a + b"
        functions = extract_functions(formula)
        self.assertEqual(len(functions), 0)


class TestParseFunction(unittest.TestCase):
    """Tests for function parsing."""
    
    def test_simple_parse(self):
        """Test parsing a simple function."""
        func_str = "SUM(10, 20)"
        name, params = parse_function(func_str)
        self.assertEqual(name, "SUM")
        self.assertEqual(len(params), 2)
        self.assertEqual(params[0], "10")
        self.assertEqual(params[1], "20")
    
    def test_nested_parse(self):
        """Test parsing a function with nested parameters."""
        func_str = "IF(x > 10, SUM(a, b), 0)"
        name, params = parse_function(func_str)
        self.assertEqual(name, "IF")
        self.assertEqual(len(params), 3)


class TestGetValue(unittest.TestCase):
    """Tests for value extraction."""
    
    def test_field_reference(self):
        """Test getting value from field reference."""
        record = {"field1": 100, "field2": "test"}
        self.assertEqual(get_value("field1", record), 100)
        self.assertEqual(get_value("field2", record), "test")
    
    def test_numeric_literal(self):
        """Test numeric literals."""
        record = {}
        self.assertEqual(get_value("123", record), 123.0)
        self.assertEqual(get_value("45.67", record), 45.67)
    
    def test_string_literal(self):
        """Test string literals."""
        record = {}
        self.assertEqual(get_value('"hello"', record), "hello")
    
    def test_boolean_literals(self):
        """Test boolean literals."""
        record = {}
        self.assertTrue(get_value("True", record))
        self.assertFalse(get_value("False", record))
    
    def test_empty_value(self):
        """Test empty value."""
        record = {}
        self.assertIsNone(get_value("", record))


class TestProcessFormula(unittest.TestCase):
    """Tests for formula processing."""
    
    def test_simple_arithmetic(self):
        """Test processing simple arithmetic formula."""
        record = {"a": 10, "b": 20}
        result = process_formula("a + b", "result", record)
        self.assertEqual(result, 30)
    
    def test_field_reference(self):
        """Test processing with field reference."""
        record = {"price": 100}
        result = process_formula("price * 2", "total", record)
        self.assertEqual(result, 200)


if __name__ == '__main__':
    unittest.main()
