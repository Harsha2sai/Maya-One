import logging
import asyncio
import requests
import math
import re
import urllib.parse
from typing import Optional
from livekit.agents import function_tool, RunContext

logger = logging.getLogger(__name__)

@function_tool()
async def calculate(context: RunContext, expression: str) -> str:
    """
    Perform a mathematical calculation.

    Args:
        expression: The mathematical expression to evaluate (e.g., "2 + 2", "sqrt(16) * 5")
    """
    logger.info(f"Calculating: {expression}")
    try:
        # Allow only safe characters
        if not re.match(r'^[0-9+\-*/().\s,**]+$', expression):
            # Check if it contains math functions
            allowed_math_funcs = ['sqrt', 'log', 'log10', 'sin', 'cos', 'tan', 'pi', 'e', 'pow']
            clean_expr = expression
            for func in allowed_math_funcs:
                clean_expr = clean_expr.replace(func, '')

            if not re.match(r'^[0-9+\-*/().\s,**]+$', clean_expr):
                return "Error: Expression contains forbidden characters or functions."

        # Prepare safe namespace
        safe_dict = {
            'sqrt': math.sqrt,
            'log': math.log,
            'log10': math.log10,
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'pi': math.pi,
            'e': math.e,
            'pow': pow,
            'abs': abs,
            'round': round,
        }

        # Evaluate
        result = eval(expression, {"__builtins__": None}, safe_dict)
        return f"The result of {expression} is {result}"
    except Exception as e:
        logger.error(f"Calculation error: {e}")
        return f"Error calculating {expression}: {str(e)}"

@function_tool()
async def wikipedia_search(context: RunContext, query: str) -> str:
    """
    Search Wikipedia for a summary of a topic.

    Args:
        query: The topic to search for.
    """
    logger.info(f"Wikipedia search for: {query}")
    try:
        # Use Wikipedia REST API
        encoded_query = urllib.parse.quote(query.replace(' ', '_'))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_query}"

        def _fetch():
            headers = {
                'User-Agent': 'MayaAgent/1.0 (https://maya.ai; support@maya.ai)'
            }
            return requests.get(url, headers=headers, timeout=5)

        response = await asyncio.to_thread(_fetch)

        if response.status_code == 200:
            data = response.json()
            extract = data.get('extract')
            if extract:
                return f"According to Wikipedia: {extract}"
            return f"I found a page for '{query}', but no summary was available."
        elif response.status_code == 404:
            return f"I couldn't find any Wikipedia article for '{query}'."
        else:
            return f"Failed to retrieve information from Wikipedia (Status: {response.status_code})."
    except Exception as e:
        logger.error(f"Wikipedia search error: {e}")
        return f"An error occurred while searching Wikipedia: {str(e)}"

@function_tool()
async def convert_units(context: RunContext, value: float, from_unit: str, to_unit: str) -> str:
    """
    Convert a value from one unit to another.

    Args:
        value: The numeric value to convert.
        from_unit: The source unit (e.g., "celsius", "meters", "kilograms", "miles").
        to_unit: The target unit (e.g., "fahrenheit", "feet", "pounds", "kilometers").
    """
    logger.info(f"Converting {value} {from_unit} to {to_unit}")

    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()

    # Temperature
    if from_unit == "celsius" and to_unit == "fahrenheit":
        res = (value * 9/5) + 32
        return f"{value} Celsius is {res:.2f} Fahrenheit"
    if from_unit == "fahrenheit" and to_unit == "celsius":
        res = (value - 32) * 5/9
        return f"{value} Fahrenheit is {res:.2f} Celsius"

    # Distance
    dist_map = {
        "meters": 1.0,
        "kilometers": 1000.0,
        "centimeters": 0.01,
        "millimeters": 0.001,
        "miles": 1609.34,
        "feet": 0.3048,
        "inches": 0.0254,
        "yards": 0.9144
    }

    if from_unit in dist_map and to_unit in dist_map:
        value_in_meters = value * dist_map[from_unit]
        res = value_in_meters / dist_map[to_unit]
        return f"{value} {from_unit} is {res:.2f} {to_unit}"

    # Weight
    weight_map = {
        "kilograms": 1.0,
        "grams": 0.001,
        "milligrams": 0.000001,
        "pounds": 0.453592,
        "ounces": 0.0283495
    }

    if from_unit in weight_map and to_unit in weight_map:
        value_in_kg = value * weight_map[from_unit]
        res = value_in_kg / weight_map[to_unit]
        return f"{value} {from_unit} is {res:.2f} {to_unit}"

    return f"I don't know how to convert from {from_unit} to {to_unit} yet."

@function_tool()
async def convert_currency(
    context: RunContext,
    amount: float,
    from_currency: str,
    to_currency: str
) -> str:
    """
    Convert an amount from one currency to another.

    Args:
        amount: The amount of money to convert.
        from_currency: The source currency code (e.g., "USD", "EUR", "GBP", "INR").
        to_currency: The target currency code (e.g., "JPY", "CAD", "AUD").
    """
    from_currency = from_currency.upper().strip()
    to_currency = to_currency.upper().strip()

    logger.info(f"Converting currency: {amount} {from_currency} to {to_currency}")

    try:
        # Use a free API (no key required for some basic endpoints)
        url = f"https://open.er-api.com/v6/latest/{from_currency}"

        def _fetch():
            return requests.get(url, timeout=5)

        response = await asyncio.to_thread(_fetch)

        if response.status_code == 200:
            data = response.json()
            if data.get("result") == "success":
                rates = data.get("rates", {})
                if to_currency in rates:
                    rate = rates[to_currency]
                    result = amount * rate
                    return f"{amount} {from_currency} is approximately {result:.2f} {to_currency} (Rate: {rate:.4f})"
                else:
                    return f"Currency code '{to_currency}' not found."
            else:
                return f"Failed to get exchange rates for {from_currency}."
        else:
            return f"Currency API error (Status: {response.status_code})."
    except Exception as e:
        logger.error(f"Currency conversion error: {e}")
        return f"An error occurred during currency conversion: {str(e)}"
