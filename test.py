from fastmcp import FastMCP

mcp = FastMCP("Demo 🚀")

@mcp.tool
def multiple(a: int, b: int) -> int:
    """整数相乘"""
    return a * b

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8765
    )
