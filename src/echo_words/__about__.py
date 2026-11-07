__version__ = "1.16.0"

# Wikimedia refuses every request whose agent gives no way to reach the operator,
# httpx's default among them.
USER_AGENT = f"echo-words/{__version__} (https://github.com/andgineer/echo-words)"
