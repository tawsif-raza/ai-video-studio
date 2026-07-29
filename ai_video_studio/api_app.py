import uvicorn

from web_api import create_app

app = create_app()


def main():
    uvicorn.run("api_app:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
