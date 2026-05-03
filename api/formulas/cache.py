"""
Caching utilities for formula processing.

This module provides caching mechanisms to improve performance
of formula validation and evaluation.
"""
import functools
from typing import Any, Callable


def memoize(func: Callable) -> Callable:
    """
    Simple memoization decorator for caching function results.
    
    Args:
        func: The function to memoize
        
    Returns:
        Wrapped function with caching
    """
    cache = {}
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Create a cache key from args and kwargs
        key = str(args) + str(sorted(kwargs.items()))
        
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        
        return cache[key]
    
    return wrapper


class FormulaCache:
    """
    Cache for parsed formulas to avoid redundant parsing.
    
    This cache stores parsed formula structures to improve performance
    when the same formula is evaluated multiple times.
    """
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize the formula cache.
        
        Args:
            max_size: Maximum number of cached formulas
        """
        self._cache = {}
        self._max_size = max_size
        self._access_count = {}
    
    def get(self, formula: str) -> Any:
        """
        Get a cached formula result.
        
        Args:
            formula: The formula string
            
        Returns:
            Cached result if available, None otherwise
        """
        if formula in self._cache:
            self._access_count[formula] = self._access_count.get(formula, 0) + 1
            return self._cache[formula]
        return None
    
    def set(self, formula: str, result: Any) -> None:
        """
        Cache a formula result.
        
        Args:
            formula: The formula string
            result: The result to cache
        """
        if len(self._cache) >= self._max_size:
            # Evict least recently used item
            min_key = min(self._access_count, key=self._access_count.get)
            del self._cache[min_key]
            del self._access_count[min_key]
        
        self._cache[formula] = result
        self._access_count[formula] = 1
    
    def clear(self) -> None:
        """Clear all cached formulas."""
        self._cache.clear()
        self._access_count.clear()
    
    def size(self) -> int:
        """Get the current cache size."""
        return len(self._cache)


# Global formula cache instance
_formula_cache = FormulaCache()


def get_formula_cache() -> FormulaCache:
    """Get the global formula cache instance."""
    return _formula_cache
