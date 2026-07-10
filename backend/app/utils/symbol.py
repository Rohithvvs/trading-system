def canonical_symbol(raw_symbol: str) -> str:
    """
    Normalizes any symbol format to a canonical internal format.
    Strips 'NSE:' or 'BSE:' prefixes.
    Strips '-EQ' suffix.
    Maintains '-INDEX' or other suffixes.
    
    Examples:
        'NSE:DATAPATTNS-EQ' -> 'DATAPATTNS'
        'DATAPATTNS-EQ' -> 'DATAPATTNS'
        'DATAPATTNS' -> 'DATAPATTNS'
        'nse:datapattns-eq' -> 'DATAPATTNS'
        'NSE:NIFTY50-INDEX' -> 'NIFTY50-INDEX'
    """
    if not raw_symbol:
        return ""
    
    s = raw_symbol.strip().upper()
    
    # Strip exchange prefixes
    if s.startswith("NSE:"):
        s = s[4:]
    elif s.startswith("BSE:"):
        s = s[4:]
    elif ":" in s:
        s = s.split(":", 1)[1]
        
    # Strip -EQ suffix
    if s.endswith("-EQ"):
        s = s[:-3]
        
    return s

def fyers_symbol(canonical: str, is_index: bool = False, exchange: str = "NSE") -> str:
    """
    Converts a canonical symbol to FYERS API format.
    Appends '-EQ' unless it's an index or already has a suffix.
    
    Examples:
        'DATAPATTNS' -> 'NSE:DATAPATTNS-EQ'
        'NIFTY50-INDEX' -> 'NSE:NIFTY50-INDEX'
    """
    if not canonical:
        return ""
        
    s = canonical.strip().upper()
    
    # If it's already a fully qualified FYERS symbol, return as is
    if ":" in s:
        return s
        
    # Check for known suffixes
    has_suffix = "-" in s
    
    if is_index and not has_suffix:
        s = f"{s}-INDEX"
    elif not has_suffix:
        s = f"{s}-EQ"
        
    return f"{exchange}:{s}"
