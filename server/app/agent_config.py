import json

from agents import Agent, WebSearchTool, function_tool
from agents.tool import UserLocation

import app.mock_api as mock_api
from app.softnix_api import query_softnix_genai, SoftnixAPIError

STYLE_INSTRUCTIONS = "Use a conversational tone and write in a chat style without formal formatting or lists and do not use any emojis."


@function_tool
def get_past_orders():
    return json.dumps(mock_api.get_past_orders())


@function_tool
def submit_refund_request(order_number: str):
    """Confirm with the user first"""
    return mock_api.submit_refund_request(order_number)


@function_tool
def get_softnix_info(question: str):
    """
    Get information about Softnix products, services, or company from the Softnix GenAI knowledge base.

    Use this tool when the user asks about:
    - Softnix products or services
    - Company information
    - Pricing or packages
    - Technical specifications
    - How to use Softnix services

    Args:
        question: The user's question about Softnix

    Returns:
        Answer from Softnix GenAI knowledge base
    """
    try:
        return query_softnix_genai(question)
    except SoftnixAPIError as e:
        return f"I apologize, but I'm having trouble accessing the Softnix information system right now. Error: {str(e)}"


customer_support_agent = Agent(
    name="Customer Support Agent",
    instructions=f"You are a customer support assistant. {STYLE_INSTRUCTIONS}",
    model="gpt-4o-mini",
    tools=[get_past_orders, submit_refund_request],
)

softnix_sales_agent = Agent(
    name="Softnix Sales Agent",
    model="gpt-4o-mini",
    instructions=f"""You are a Softnix sales representative assistant.
    You help customers understand Softnix products and services by answering their questions.

    When a customer asks about Softnix products, services, pricing, or company information,
    use the get_softnix_info tool to retrieve accurate information from the knowledge base.

    Be helpful, professional, and informative. If a customer wants to place an order or
    needs customer support after purchase, you can transfer them to the Customer Support Agent.

    {STYLE_INSTRUCTIONS}""",
    tools=[get_softnix_info],
    handoffs=[customer_support_agent],
)

stylist_agent = Agent(
    name="Stylist Agent",
    model="gpt-4o-mini",
    instructions=f"You are a stylist assistant. {STYLE_INSTRUCTIONS}",
    tools=[WebSearchTool(user_location=UserLocation(type="approximate", city="Bangkok"))],
    handoffs=[customer_support_agent],
)

triage_agent = Agent(
    name="Triage Agent",
    model="gpt-4o-mini",
    instructions=f"""Route the user to the appropriate agent based on their request.

    Transfer to:
    - Softnix Sales Agent: Questions about Softnix products, services, or company information
    - Stylist Agent: Fashion advice, clothing recommendations, style questions
    - Customer Support Agent: Order history, refunds, purchase issues

    {STYLE_INSTRUCTIONS}""",
    handoffs=[softnix_sales_agent, stylist_agent, customer_support_agent],
)

starting_agent = triage_agent
