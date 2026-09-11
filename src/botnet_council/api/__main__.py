"""Conservative local development entry point for the optional API."""


def main() -> None:
    import uvicorn

    uvicorn.run(
        "botnet_council.api.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
    )


if __name__ == "__main__":
    main()
