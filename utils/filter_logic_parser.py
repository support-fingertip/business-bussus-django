import re
from typing import List, Dict, Any

def parse_filter_logic(logic_string: str, filters: List[Dict]) -> Dict: 
    """
    Parses filter logic string like "1 AND (2 OR NOT 3)" into nested dict structure.
    
    Args:
        logic_string: Logic expression with filter IDs
        filters: List of filter objects with IDs
        
    Returns:
        Nested dict structure for query builder
    """
    # Create filter ID mapping
    filter_map = {i + 1: f for i, f in enumerate(filters)}
    
    # Tokenize the logic string
    tokens = tokenize_logic(logic_string)
    
    # Build expression tree
    tree = build_expression_tree(tokens, filter_map)
    
    return tree


def tokenize_logic(logic_string: str) -> List[str]:
    """
    Tokenizes logic string into operators and operands.
    
    Example: "1 AND (2 OR NOT 3)" -> ['1', 'AND', '(', '2', 'OR', 'NOT', '3', ')']
    """
    # Replace operators with standardized versions
    logic_string = logic_string.upper()
    
    # Tokenize:  numbers, operators, parentheses
    pattern = r'(\d+|AND|OR|NOT|\(|\))'
    tokens = re.findall(pattern, logic_string)
    
    return tokens


def build_expression_tree(tokens: List[str], filter_map: Dict[int, Dict]) -> Dict:
    """
    Builds an expression tree from tokens using recursive descent parsing.
    
    Grammar:
        expr    := term (OR term)*
        term    := factor (AND factor)*
        factor  := NOT factor | atom
        atom    := NUMBER | '(' expr ')'
    """
    tokens = tokens[:]  # Copy to avoid mutation
    
    def parse_expr():
        """Parse OR expressions (lowest precedence)"""
        left = parse_term()
        
        or_terms = [left]
        while tokens and tokens[0] == 'OR': 
            tokens.pop(0)  # consume 'OR'
            or_terms.append(parse_term())
        
        if len(or_terms) == 1:
            return or_terms[0]
        return {"or": or_terms}
    
    def parse_term():
        """Parse AND expressions (medium precedence)"""
        left = parse_factor()
        
        and_factors = [left]
        while tokens and tokens[0] == 'AND':
            tokens.pop(0)  # consume 'AND'
            and_factors.append(parse_factor())
        
        if len(and_factors) == 1:
            return and_factors[0]
        return {"and": and_factors}
    
    def parse_factor():
        """Parse NOT expressions (high precedence)"""
        if tokens and tokens[0] == 'NOT':
            tokens.pop(0)  # consume 'NOT'
            return {"not": parse_factor()}
        return parse_atom()
    
    def parse_atom():
        """Parse numbers or parenthesized expressions"""
        if not tokens:
            raise ValueError("Unexpected end of expression")
        
        token = tokens. pop(0)
        
        # Handle parentheses
        if token == '(':
            expr = parse_expr()
            if not tokens or tokens. pop(0) != ')':
                raise ValueError("Mismatched parentheses")
            return expr
        
        # Handle filter ID
        if token.isdigit():
            filter_id = int(token)
            if filter_id not in filter_map:
                raise ValueError(f"Filter ID {filter_id} not found")
            return filter_map[filter_id]
        
        raise ValueError(f"Unexpected token:  {token}")
    
    return parse_expr()


def convert_to_query_format(filters: List[Dict], filter_logic: str = None) -> Dict:
    """
    Main entry point:  converts filters + logic string to query builder format. 
    
    Args:
        filters: List of filter objects
        filter_logic: Optional logic string like "1 AND (2 OR NOT 3)"
        
    Returns:
        Nested dict compatible with build_nested_criteria()
    """
    if not filter_logic or not filter_logic.strip():
        # Default:  AND all filters
        return {"and": filters} if len(filters) > 1 else filters[0] if filters else {}
    
    try:
        return parse_filter_logic(filter_logic, filters)
    except Exception as e:
        raise ValueError(f"Invalid filter logic: {e}")


# Example usage:
if __name__ == "__main__": 
    filters = [
        {"field": "grand_total", "value": "7000", "operator":  "greater_than"},
        {"field": "status", "value":  "overdue", "operator": "equals"},
        {"field": "store_id", "value": "acC_6H3aemCfXs", "operator": "equals"}
    ]
    
    logic = "1 AND (2 OR NOT 3)"
    result = convert_to_query_format(filters, logic)
    print(result)
    
    # Output:
    # {
    #     "and": [
    #         {"field": "grand_total", "value": "7000", "operator": "greater_than"},
    #         {
    #             "or": [
    #                 {"field": "status", "value":  "overdue", "operator": "equals"},
    #                 {
    #                     "not": {"field": "store_id", "value": "acC_6H3aemCfXs", "operator": "equals"}
    #                 }
    #             ]
    #         }
    #     ]
    # }