from mcp.server.fastmcp import FastMCP
import random

mcp = FastMCP("India Native")

@mcp.tool()
async def check_pnr_status(pnr_number: str) -> str:
    """Check the current status of an Indian Railways PNR number."""
    if not pnr_number.isdigit() or len(pnr_number) != 10:
        return "Error: Invalid PNR format. PNR must be a 10-digit number."

    # Simulated PNR data
    train_names = ["Telangana Express", "Godavari Express", "Rajdhani Express", "Shatabdi Express"]
    train = random.choice(train_names)
    status_options = ["CNF/B1/42/NO", "RAC/3/4", "WL/45/WL/22"]
    status = random.choice(status_options)

    return f"PNR: {pnr_number}\nTrain: {train}\nStatus: {status}\nDate: 25-12-2025"

@mcp.tool()
async def generate_upi_link(vpa: str, amount: float, name: str = "") -> str:
    """Generate a UPI payment link/QR data."""
    if "@" not in vpa:
        return "Error: Invalid UPI ID (VPA)."

    clean_name = name.replace(" ", "%20")
    upi_url = f"upi://pay?pa={vpa}&pn={clean_name}&am={amount:.2f}&cu=INR"
    return f"UPI Link: {upi_url}\nTo pay ₹{amount:.2f} to {vpa}"

@mcp.tool()
async def book_irctc_ticket(train_no: str, date: str, quota: str = "GN") -> str:
    """Initiate an IRCTC ticket booking request."""
    return f"Booking request for Train {train_no} on {date} under {quota} quota has been initiated. Redirecting to payment..."

@mcp.tool()
async def check_tsrtc_bus_availability(source: str, destination: str, date: str) -> str:
    """Check availability for TSRTC (Telangana State Road Transport) buses."""
    return f"Found 5 buses from {source} to {destination} on {date}.\n1. Garuda Plus - 22:30 (12 seats)\n2. Super Luxury - 23:00 (5 seats)"

if __name__ == "__main__":
    mcp.run()
