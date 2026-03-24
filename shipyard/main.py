import uvicorn
from shipyard.config import get_config


def run_server():
    """Entry point for `shipyard-server` command."""
    config = get_config()
    uvicorn.run(
        "shipyard.server.app:app",
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
