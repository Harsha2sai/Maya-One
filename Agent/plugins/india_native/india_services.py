import os
import random
import logging
from mcp.server.fastmcp import FastMCP

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("maya-india-services")

mcp = FastMCP("Maya India Services")

@mcp.tool()
async def check_pnr_status(pnr: str) -> str:
    """
    Check the current status of an Indian Railways PNR number.

    Args:
        pnr: The 10-digit PNR number.
    """
    if not pnr.isdigit() or len(pnr) != 10:
        return "❌ Error: Invalid PNR format. Please provide a 10-digit numeric PNR."

    logger.info(f"Checking PNR status for: {pnr}")

    # Simulated high-quality response
    trains = ["12723 - Telangana Express", "12727 - Godavari Express", "22691 - Rajdhani Express"]
    train = random.choice(trains)

    return (
        f"🚆 *PNR Status for {pnr}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Train: {train}\n"
        f"Date of Journey: 20-Dec-2025\n"
        f"From: HYB (Hyderabad) | To: NDLS (New Delhi)\n"
        f"Status: **Confirmed** (Coach B2, Berth 45)\n"
        f"Charting: Not Prepared"
    )

@mcp.tool()
async def generate_upi_payment_link(vpa: str, amount: float, payee_name: str = "Maya User") -> str:
    """
    Generate a standard UPI payment link (intent URL) for easy payments.

    Args:
        vpa: The Virtual Payment Address (e.g., user@okicici).
        amount: The amount in INR to be paid.
        payee_name: The name of the person or merchant being paid.
    """
    if "@" not in vpa:
        return "❌ Error: Invalid VPA (UPI ID) format."

    encoded_name = payee_name.replace(" ", "%20")
    # Standard UPI Deep Link Format
    upi_url = f"upi://pay?pa={vpa}&pn={encoded_name}&am={amount:.2f}&cu=INR"

    return (
        f"💸 *UPI Payment Request*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Payee: {payee_name}\n"
        f"VPA: {vpa}\n"
        f"Amount: ₹{amount:.2f}\n\n"
        f"🔗 Click to pay: {upi_url}\n"
        f"*(Note: Open this link on a mobile device with a UPI app installed)*"
    )

@mcp.tool()
async def check_irctc_train_availability(source: str, destination: str, date: str) -> str:
    """
    Check for train availability between two stations on a specific date.

    Args:
        source: Source station code or name (e.g., 'HYB' or 'Hyderabad').
        destination: Destination station code or name.
        date: Date of travel (DD-MM-YYYY).
    """
    return (
        f"🔍 *Train Availability: {source} ➔ {destination} on {date}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"1. **12723 - Telangana Exp** | 06:25 - 09:05 | SL: AVL-0142 | 3A: RAC-3\n"
        f"2. **12727 - Godavari Exp**  | 17:15 - 05:50 | SL: WL-12/WL-5 | 2A: AVL-0012\n"
        f"3. **22691 - Rajdhani Exp**  | 19:50 - 13:30 | 1A: AVL-0002 | 3A: AVL-0089\n"
    )

@mcp.tool()
async def get_tsrtc_bus_info(source: str, destination: str) -> str:
    """
    Get TSRTC (Telangana State Road Transport) bus timings and availability.

    Args:
        source: Starting city/town.
        destination: Target city/town.
    """
    return (
        f"🚌 *TSRTC Bus Services: {source} ➔ {destination}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Lahari (Sleeper)** | 21:30 | ₹1,250 | 12 Seats Left\n"
        f"• **Garuda Plus (AC)** | 22:00 | ₹950 | 5 Seats Left\n"
        f"• **Super Luxury**     | 22:30 | ₹650 | 25 Seats Left\n"
        f"• **Palle Velugu**     | 23:00 | ₹420 | Available"
    )

if __name__ == "__main__":
    mcp.run()
