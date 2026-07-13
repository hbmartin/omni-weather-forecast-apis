import csv
import logging
import sys


def file_handlers() -> None:
    # ruleid: cli-filehandler-requires-utf8
    logging.FileHandler("weather.log")
    # ok: cli-filehandler-requires-utf8
    logging.FileHandler("weather.log", encoding="utf-8")


def csv_writers() -> None:
    # ruleid: cli-stdout-csv-requires-line-terminator
    csv.DictWriter(sys.stdout, fieldnames=["temperature"])
    # ok: cli-stdout-csv-requires-line-terminator
    csv.DictWriter(
        sys.stdout,
        fieldnames=["temperature"],
        lineterminator="\n",
    )
