import os

import uvicorn

from web_api import create_app

app = create_app()


def main():
    # Railway (and most PaaS containers) inject PORT dynamically and expect
    # the process to bind 0.0.0.0, not loopback - HOST/PORT are overridable,
    # defaulting to the previous local-dev values' equivalent container-safe
    # form. In production, Railway's start command invokes uvicorn directly
    # (see railway.json) and never calls this function; it's kept working
    # for `python api_app.py` local/manual use too.
    uvicorn.run("api_app:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
