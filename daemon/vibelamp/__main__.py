import logging
from .server import serve


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    serve()


if __name__ == "__main__":
    main()
